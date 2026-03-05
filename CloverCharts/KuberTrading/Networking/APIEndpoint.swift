import Foundation

enum HTTPMethod: String {
    case get = "GET"
    case post = "POST"
    case put = "PUT"
    case patch = "PATCH"
    case delete = "DELETE"
}

enum APIEndpoint {
    // MARK: - Auth

    case login(UserLogin)
    case register(UserCreate)

    // MARK: - Users

    case getCurrentUser
    case updateCurrentUser(UserUpdate)
    case getSubscription
    case getTelegramConfig
    case updateTelegramConfig(TelegramConfig)
    case testTelegram
    case deleteTelegram
    case registerDevice(DeviceRegistration)
    case unregisterDevice(deviceId: String)

    // MARK: - Health

    case healthCheck
    case healthServices
    case healthReady

    // MARK: - Dashboard

    case getDashboard(timezone: String?)

    // MARK: - Pipelines

    case listPipelines
    case createPipeline(PipelineCreate)
    case getPipeline(id: String)
    case updatePipeline(id: String, PipelineUpdate)
    case deletePipeline(id: String)

    // MARK: - Executions

    case createExecution(ExecutionCreate)
    case listExecutions(limit: Int?, offset: Int?, pipelineId: String?, status: String?, tradeOutcome: String?)
    case getExecutionStats
    case getExecution(id: String)
    case stopExecution(id: String)
    case closePosition(id: String)
    case reconcileExecution(id: String)
    case resumeMonitoring(id: String)
    case getExecutionLogs(id: String)
    case pauseExecution(id: String)
    case resumeExecution(id: String)
    case cancelExecution(id: String)
    case getExecutiveReport(id: String)
    case getTradeAnalysis(id: String)
    case downloadReportPDF(id: String)

    // MARK: - Agents

    case listAgents
    case getAgentsByCategory(category: String)
    case getAgent(agentType: String)
    case validateInstructions(ValidateInstructionsRequest)
    case getAvailableTools

    // MARK: - Tools

    case listTools
    case getToolsByCategory(category: String)
    case getTool(toolType: String)

    // MARK: - Scanners

    case listScanners
    case createScanner(ScannerCreate)
    case getScanner(id: String)
    case updateScanner(id: String, ScannerUpdate)
    case deleteScanner(id: String)
    case getScannerTickers(id: String)
    case getScannerUsage(id: String)

    // MARK: - Signals

    case getSignalTypes

    // MARK: - Approvals (token-based, no JWT auth)

    case approveExecution(executionId: String, token: String)
    case rejectExecution(executionId: String, token: String)
    case getPreTradeReport(executionId: String, token: String)

    // MARK: - Files

    case uploadFile(Data, filename: String)
    case downloadFile(path: String)
    case deleteFile(path: String)

    // MARK: - Path

    var path: String {
        switch self {
        // Auth
        case .login:
            return "/auth/login"
        case .register:
            return "/auth/register"

        // Users
        case .getCurrentUser:
            return "/users/me"
        case .updateCurrentUser:
            return "/users/me"
        case .getSubscription:
            return "/users/me/subscription"
        case .getTelegramConfig:
            return "/users/me/telegram"
        case .updateTelegramConfig:
            return "/users/me/telegram"
        case .testTelegram:
            return "/users/me/telegram/test"
        case .deleteTelegram:
            return "/users/me/telegram"
        case .registerDevice:
            return "/users/me/devices"
        case .unregisterDevice(let deviceId):
            return "/users/me/devices/\(deviceId)"

        // Health
        case .healthCheck:
            return "/health/"
        case .healthServices:
            return "/health/services"
        case .healthReady:
            return "/health/ready"

        // Dashboard
        case .getDashboard:
            return "/dashboard/"

        // Pipelines
        case .listPipelines:
            return "/pipelines"
        case .createPipeline:
            return "/pipelines"
        case .getPipeline(let id):
            return "/pipelines/\(id)"
        case .updatePipeline(let id, _):
            return "/pipelines/\(id)"
        case .deletePipeline(let id):
            return "/pipelines/\(id)"

        // Executions
        case .createExecution:
            return "/executions/"
        case .listExecutions:
            return "/executions/"
        case .getExecutionStats:
            return "/executions/stats"
        case .getExecution(let id):
            return "/executions/\(id)"
        case .stopExecution(let id):
            return "/executions/\(id)/stop"
        case .closePosition(let id):
            return "/executions/\(id)/close-position"
        case .reconcileExecution(let id):
            return "/executions/\(id)/reconcile"
        case .resumeMonitoring(let id):
            return "/executions/\(id)/resume-monitoring"
        case .getExecutionLogs(let id):
            return "/executions/\(id)/logs"
        case .pauseExecution(let id):
            return "/executions/\(id)/pause"
        case .resumeExecution(let id):
            return "/executions/\(id)/resume"
        case .cancelExecution(let id):
            return "/executions/\(id)/cancel"
        case .getExecutiveReport(let id):
            return "/executions/\(id)/executive-report"
        case .getTradeAnalysis(let id):
            return "/executions/\(id)/trade-analysis"
        case .downloadReportPDF(let id):
            return "/executions/\(id)/report.pdf"

        // Agents
        case .listAgents:
            return "/agents"
        case .getAgentsByCategory(let category):
            return "/agents/category/\(category)"
        case .getAgent(let agentType):
            return "/agents/\(agentType)"
        case .validateInstructions:
            return "/agents/validate-instructions"
        case .getAvailableTools:
            return "/agents/tools/available"

        // Tools
        case .listTools:
            return "/tools/"
        case .getToolsByCategory(let category):
            return "/tools/category/\(category)"
        case .getTool(let toolType):
            return "/tools/\(toolType)"

        // Scanners
        case .listScanners:
            return "/scanners"
        case .createScanner:
            return "/scanners"
        case .getScanner(let id):
            return "/scanners/\(id)"
        case .updateScanner(let id, _):
            return "/scanners/\(id)"
        case .deleteScanner(let id):
            return "/scanners/\(id)"
        case .getScannerTickers(let id):
            return "/scanners/\(id)/tickers"
        case .getScannerUsage(let id):
            return "/scanners/\(id)/usage"

        // Signals
        case .getSignalTypes:
            return "/scanners/signals/types"

        // Approvals
        case .approveExecution(let executionId, _):
            return "/approvals/\(executionId)/approve"
        case .rejectExecution(let executionId, _):
            return "/approvals/\(executionId)/reject"
        case .getPreTradeReport(let executionId, _):
            return "/approvals/\(executionId)/pre-trade-report"

        // Files
        case .uploadFile:
            return "/files/upload"
        case .downloadFile:
            return "/files/download"
        case .deleteFile:
            return "/files/delete"
        }
    }

    // MARK: - HTTP Method

    var method: HTTPMethod {
        switch self {
        // POST
        case .login, .register, .testTelegram, .registerDevice,
             .createPipeline, .createExecution,
             .stopExecution, .closePosition, .reconcileExecution, .resumeMonitoring,
             .pauseExecution, .resumeExecution, .cancelExecution,
             .validateInstructions, .createScanner,
             .approveExecution, .rejectExecution,
             .uploadFile:
            return .post

        // PUT
        case .updateCurrentUser, .updateTelegramConfig:
            return .put

        // PATCH
        case .updatePipeline, .updateScanner:
            return .patch

        // DELETE
        case .deleteTelegram, .unregisterDevice,
             .deletePipeline, .deleteScanner, .deleteFile:
            return .delete

        // GET (default)
        case .getCurrentUser, .getSubscription, .getTelegramConfig,
             .healthCheck, .healthServices, .healthReady,
             .getDashboard,
             .listPipelines, .getPipeline,
             .listExecutions, .getExecutionStats, .getExecution,
             .getExecutionLogs, .getExecutiveReport, .getTradeAnalysis, .downloadReportPDF,
             .listAgents, .getAgentsByCategory, .getAgent, .getAvailableTools,
             .listTools, .getToolsByCategory, .getTool,
             .listScanners, .getScanner, .getScannerTickers, .getScannerUsage,
             .getSignalTypes,
             .getPreTradeReport,
             .downloadFile:
            return .get
        }
    }

    // MARK: - Request Body

    var body: (any Encodable)? {
        switch self {
        case .login(let credentials):
            return credentials
        case .register(let user):
            return user
        case .updateCurrentUser(let update):
            return update
        case .updateTelegramConfig(let config):
            return config
        case .registerDevice(let registration):
            return registration
        case .createPipeline(let pipeline):
            return pipeline
        case .updatePipeline(_, let update):
            return update
        case .createExecution(let execution):
            return execution
        case .validateInstructions(let request):
            return request
        case .createScanner(let scanner):
            return scanner
        case .updateScanner(_, let update):
            return update
        default:
            return nil
        }
    }

    // MARK: - Requires Auth

    var requiresAuth: Bool {
        switch self {
        // Public endpoints
        case .login, .register,
             .healthCheck, .healthServices, .healthReady,
             .approveExecution, .rejectExecution, .getPreTradeReport:
            return false
        default:
            return true
        }
    }

    // MARK: - Query Items

    var queryItems: [URLQueryItem]? {
        switch self {
        case .getDashboard(let timezone):
            guard let timezone else { return nil }
            return [URLQueryItem(name: "timezone", value: timezone)]

        case .listExecutions(let limit, let offset, let pipelineId, let status, let tradeOutcome):
            var items: [URLQueryItem] = []
            if let limit {
                items.append(URLQueryItem(name: "limit", value: String(limit)))
            }
            if let offset {
                items.append(URLQueryItem(name: "offset", value: String(offset)))
            }
            if let pipelineId {
                items.append(URLQueryItem(name: "pipeline_id", value: pipelineId))
            }
            if let status {
                items.append(URLQueryItem(name: "status", value: status))
            }
            if let tradeOutcome {
                items.append(URLQueryItem(name: "trade_outcome", value: tradeOutcome))
            }
            return items.isEmpty ? nil : items

        case .approveExecution(_, let token):
            return [URLQueryItem(name: "token", value: token)]

        case .rejectExecution(_, let token):
            return [URLQueryItem(name: "token", value: token)]

        case .getPreTradeReport(_, let token):
            return [URLQueryItem(name: "token", value: token)]

        case .downloadFile(let path):
            return [URLQueryItem(name: "path", value: path)]

        case .deleteFile(let path):
            return [URLQueryItem(name: "path", value: path)]

        default:
            return nil
        }
    }

    // MARK: - Is Form Encoded

    var isFormEncoded: Bool {
        return false
    }

    // MARK: - Is Multipart (for file upload)

    var isMultipart: Bool {
        if case .uploadFile = self { return true }
        return false
    }

    // MARK: - Multipart Data

    var multipartData: (data: Data, filename: String)? {
        if case .uploadFile(let data, let filename) = self {
            return (data, filename)
        }
        return nil
    }
}
