import Foundation
import OSLog

@Observable
final class WebSocketManager: @unchecked Sendable {
    static let shared = WebSocketManager()

    var isConnected = false
    var latestMessage: WebSocketMessage?

    private var webSocketTask: URLSessionWebSocketTask?
    private var pingTask: Task<Void, Never>?
    private var receiveTask: Task<Void, Never>?
    private var reconnectAttempts = 0
    private let maxReconnectAttempts = 5
    private var subscribedExecutionIds: Set<String> = []
    private let logger = Logger(subsystem: "com.kubertrading.app", category: "WebSocket")

    // MARK: - Message Stream

    private let lock = NSLock()
    private var continuations: [UUID: AsyncStream<WebSocketMessage>.Continuation] = [:]

    func messageStream() -> AsyncStream<WebSocketMessage> {
        let id = UUID()
        return AsyncStream { [weak self] continuation in
            self?.lock.lock()
            self?.continuations[id] = continuation
            self?.lock.unlock()

            continuation.onTermination = { [weak self] _ in
                self?.lock.lock()
                self?.continuations.removeValue(forKey: id)
                self?.lock.unlock()
            }
        }
    }

    private func broadcastMessage(_ message: WebSocketMessage) {
        lock.lock()
        let activeContinuations = continuations.values
        lock.unlock()
        for continuation in activeContinuations {
            continuation.yield(message)
        }
    }

    // MARK: - Connect

    func connect() async {
        guard webSocketTask == nil else {
            logger.debug("WebSocket already connected or connecting")
            return
        }

        guard let token = try? await KeychainService.shared.read(.accessToken),
              !token.isEmpty else {
            logger.warning("No auth token available for WebSocket connection")
            return
        }

        var components = URLComponents(url: AppConfiguration.shared.wsURL, resolvingAgainstBaseURL: true)
        components?.queryItems = [URLQueryItem(name: "token", value: token)]

        guard let url = components?.url else {
            logger.error("Failed to construct WebSocket URL")
            return
        }

        let session = URLSession(configuration: .default)
        let task = session.webSocketTask(with: url)
        webSocketTask = task
        task.resume()

        reconnectAttempts = 0
        isConnected = true
        logger.info("WebSocket connected to \(url.absoluteString)")

        // Re-subscribe to any previously subscribed execution IDs
        for executionId in subscribedExecutionIds {
            send(WebSocketCommand(action: "subscribe", executionId: executionId))
        }

        receiveMessages()
        startPing()
    }

    // MARK: - Disconnect

    func disconnect() {
        pingTask?.cancel()
        pingTask = nil
        receiveTask?.cancel()
        receiveTask = nil

        webSocketTask?.cancel(with: .goingAway, reason: nil)
        webSocketTask = nil

        isConnected = false
        reconnectAttempts = 0
        logger.info("WebSocket disconnected")
    }

    // MARK: - Subscribe / Unsubscribe

    func subscribeToExecution(_ executionId: String) {
        subscribedExecutionIds.insert(executionId)
        if isConnected {
            send(WebSocketCommand(action: "subscribe", executionId: executionId))
        }
    }

    func unsubscribeFromExecution(_ executionId: String) {
        subscribedExecutionIds.remove(executionId)
        if isConnected {
            send(WebSocketCommand(action: "unsubscribe", executionId: executionId))
        }
    }

    // MARK: - Receive Loop

    private func receiveMessages() {
        receiveTask?.cancel()
        receiveTask = Task { [weak self] in
            guard let self else { return }

            while !Task.isCancelled {
                guard let task = self.webSocketTask else { break }

                do {
                    let wsMessage = try await task.receive()

                    switch wsMessage {
                    case .string(let text):
                        if let data = text.data(using: .utf8) {
                            let decoder = JSONDecoder()
                            decoder.keyDecodingStrategy = .convertFromSnakeCase
                            if let message = try? decoder.decode(WebSocketMessage.self, from: data) {
                                await MainActor.run {
                                    self.latestMessage = message
                                }
                                self.broadcastMessage(message)
                            } else {
                                self.logger.warning("Failed to decode WebSocket message: \(text.prefix(200))")
                            }
                        }

                    case .data(let data):
                        let decoder = JSONDecoder()
                        decoder.keyDecodingStrategy = .convertFromSnakeCase
                        if let message = try? decoder.decode(WebSocketMessage.self, from: data) {
                            await MainActor.run {
                                self.latestMessage = message
                            }
                            self.broadcastMessage(message)
                        }

                    @unknown default:
                        self.logger.debug("Received unknown WebSocket message type")
                    }
                } catch {
                    if !Task.isCancelled {
                        self.logger.error("WebSocket receive error: \(error.localizedDescription)")
                        await MainActor.run {
                            self.isConnected = false
                        }
                        await self.reconnect()
                    }
                    break
                }
            }
        }
    }

    // MARK: - Ping

    private func startPing() {
        pingTask?.cancel()
        pingTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 30_000_000_000) // 30 seconds
                guard !Task.isCancelled else { break }

                self?.webSocketTask?.sendPing { error in
                    if let error {
                        self?.logger.warning("WebSocket ping failed: \(error.localizedDescription)")
                    }
                }
            }
        }
    }

    // MARK: - Reconnect

    private func reconnect() async {
        guard reconnectAttempts < maxReconnectAttempts else {
            logger.error("Max WebSocket reconnect attempts (\(self.maxReconnectAttempts)) reached")
            return
        }

        reconnectAttempts += 1
        let delay = pow(2.0, Double(reconnectAttempts - 1)) // 1s, 2s, 4s, 8s, 16s
        logger.info("WebSocket reconnecting in \(delay)s (attempt \(self.reconnectAttempts)/\(self.maxReconnectAttempts))")

        // Clean up old connection
        pingTask?.cancel()
        pingTask = nil
        receiveTask?.cancel()
        receiveTask = nil
        webSocketTask?.cancel(with: .abnormalClosure, reason: nil)
        webSocketTask = nil

        try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))

        guard !Task.isCancelled else { return }
        await connect()
    }

    // MARK: - Send

    private func send(_ command: WebSocketCommand) {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        guard let data = try? encoder.encode(command),
              let jsonString = String(data: data, encoding: .utf8) else {
            logger.error("Failed to encode WebSocket command")
            return
        }

        webSocketTask?.send(.string(jsonString)) { [weak self] error in
            if let error {
                self?.logger.error("WebSocket send error: \(error.localizedDescription)")
            }
        }
    }
}
