import Foundation

struct DashboardData: Codable {
    let pipelines: DashboardPipelineStats
    let executions: DashboardExecutionStats
    let pnl: DashboardPnL
    let today: DashboardToday
    let brokerAccounts: [BrokerAccount]
    let activePositions: [ActivePosition]
    let recentExecutions: [RecentExecution]
    let pipelineList: [DashboardPipeline]
    let costHistory: [CostHistoryEntry]
    let pnlHistory: [PnLHistoryEntry]
    let tradeStats: TradeStats
}

struct DashboardPipelineStats: Codable {
    let total: Int
    let active: Int
    let inactive: Int
    let signalBased: Int
    let periodic: Int
}

struct DashboardExecutionStats: Codable {
    let total: Int
    let running: Int
    let monitoring: Int
    let needsReconciliation: Int?
    let completed: Int
    let failed: Int
    let totalCost: Double
    let successRate: Double
}

struct DashboardPnL: Codable {
    let totalRealized: Double
    let totalUnrealized: Double
    let total: Double?
}

struct DashboardToday: Codable {
    let executions: Int
    let cost: Double
    let pnl: Double?
    let totalTrades: Int?
    let wins: Int?
    let losses: Int?
    let winRate: Double?
    let avgWin: Double?
    let avgLoss: Double?
    let bestTrade: Double?
    let worstTrade: Double?
}

struct BrokerAccount: Codable, Identifiable {
    var id: String { accountId }
    let brokerName: String
    let accountId: String
    let accountType: String
    let realizedPnl: Double?
    let unrealizedPnl: Double?
    let totalPnl: Double?
    let totalTrades: Int?
    let activePositions: Int?
    let pipelineCount: Int?
}

struct ActivePosition: Codable, Identifiable {
    var id: String { executionId }
    let executionId: String
    let pipelineId: String
    let pipelineName: String
    let symbol: String?
    let mode: String
    let status: String
    let startedAt: String?
    let tradeInfo: TradeInfo?
    let pnl: PnLInfo?
    let broker: BrokerInfo?
}

struct TradeInfo: Codable {
    let orderStatus: String?
    let orderType: String?
    let side: String?
    let entryPrice: Double?
    let currentPrice: Double?
    let quantity: Double?
    let unrealizedPl: Double?
    let pnlPercent: Double?
    let takeProfit: Double?
    let stopLoss: Double?
}

struct PnLInfo: Codable {
    let value: Double?
    let percent: Double?
    let type: String?
}

struct BrokerInfo: Codable {
    let toolType: String?
    let brokerName: String?
    let accountId: String?
    let accountType: String?
}

struct RecentExecution: Codable, Identifiable {
    var id: String { executionId }
    let executionId: String
    let pipelineName: String
    let symbol: String?
    let mode: String
    let status: String
    let strategyAction: String?
    let startedAt: String?
    let completedAt: String?
    let durationSeconds: Double?
    let cost: Double?
    let pnl: PnLInfo?
}

struct DashboardPipeline: Codable, Identifiable {
    let id: String
    let name: String
    let isActive: Bool
    let triggerMode: String?
    let broker: BrokerInfo?
    let totalExecutions: Int?
    let activeExecutions: Int?
    let completedExecutions: Int?
    let failedExecutions: Int?
    let totalPnl: Double?
    let createdAt: String?
}

struct CostHistoryEntry: Codable {
    let date: String
    let cost: Double
}

struct PnLHistoryEntry: Codable {
    let date: String
    let pnl: Double
}

struct TradeStats: Codable {
    let totalTrades: Int?
    let winningTrades: Int?
    let losingTrades: Int?
    let winRate: Double?
    let avgWin: Double?
    let avgLoss: Double?
    let bestTrade: Double?
    let worstTrade: Double?
    let profitFactor: Double?
}
