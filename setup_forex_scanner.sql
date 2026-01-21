-- Setup script for Forex Scanner and Pipeline
-- Run this in the trading_platform database

-- 1. Create a Forex Scanner
INSERT INTO scanners (
    id,
    user_id,
    name,
    description,
    scanner_type,
    config,
    is_active,
    created_at,
    updated_at
)
VALUES (
    gen_random_uuid(),
    (SELECT id FROM users LIMIT 1),  -- Use first user
    'Forex Major Pairs',
    'Scanner for major forex currency pairs (EUR, GBP, JPY)',
    'manual',
    '{"tickers": ["EUR_USD", "GBP_USD", "USD_JPY", "USD_CHF", "AUD_USD", "NZD_USD"], "description": "Major forex pairs from OANDA"}'::jsonb,
    true,
    NOW(),
    NOW()
)
ON CONFLICT DO NOTHING;

-- 2. Get the scanner ID (for reference)
DO $$
DECLARE
    scanner_id_var UUID;
    user_id_var UUID;
BEGIN
    SELECT id INTO scanner_id_var FROM scanners WHERE name = 'Forex Major Pairs';
    SELECT id INTO user_id_var FROM users LIMIT 1;
    
    -- 3. Create a Forex Trading Pipeline
    INSERT INTO pipelines (
        id,
        user_id,
        name,
        description,
        config,
        scanner_id,
        is_active,
        created_at,
        updated_at,
        trigger_mode
    )
    VALUES (
        gen_random_uuid(),
        user_id_var,
        'Forex RSI Reversal Strategy',
        'RSI-based mean reversion strategy for forex pairs',
        jsonb_build_object(
            'nodes', jsonb_build_array(
                -- Time Trigger Node
                jsonb_build_object(
                    'id', 'node-1',
                    'agent_type', 'time_trigger',
                    'node_category', 'agent',
                    'config', jsonb_build_object(
                        'agent_id', 'trigger-1',
                        'agent_type', 'time_trigger',
                        'schedule', '*/5 * * * *',
                        'instructions', 'Check every 5 minutes'
                    )
                ),
                -- Market Data Node
                jsonb_build_object(
                    'id', 'node-2',
                    'agent_type', 'market_data_agent',
                    'node_category', 'agent',
                    'config', jsonb_build_object(
                        'agent_id', 'data-1',
                        'agent_type', 'market_data_agent',
                        'timeframes', jsonb_build_array('5m', '15m', '1h'),
                        'instructions', 'Fetch 5-minute, 15-minute, and 1-hour candle data for forex pairs'
                    )
                ),
                -- Bias Agent Node
                jsonb_build_object(
                    'id', 'node-3',
                    'agent_type', 'bias_agent',
                    'node_category', 'agent',
                    'config', jsonb_build_object(
                        'agent_id', 'bias-1',
                        'agent_type', 'bias_agent',
                        'model', 'gpt-3.5-turbo',
                        'instructions', 'Analyze 1-hour timeframe using RSI (14) and MACD. Determine market bias: BULLISH if RSI > 50 and MACD histogram positive, BEARISH if RSI < 50 and MACD histogram negative, otherwise NEUTRAL. Use thresholds: RSI 30 (oversold) and 70 (overbought).'
                    )
                ),
                -- Strategy Agent Node
                jsonb_build_object(
                    'id', 'node-4',
                    'agent_type', 'strategy_agent',
                    'node_category', 'agent',
                    'config', jsonb_build_object(
                        'agent_id', 'strategy-1',
                        'agent_type', 'strategy_agent',
                        'model', 'gpt-3.5-turbo',
                        'instructions', 'Generate trading signals on 5-minute timeframe. Look for RSI oversold (<30) for BUY signals if bias is BULLISH, RSI overbought (>70) for SELL signals if bias is BEARISH. Set stop loss at 20 pips and take profit at 40 pips (2:1 risk/reward).'
                    )
                ),
                -- Risk Manager Node
                jsonb_build_object(
                    'id', 'node-5',
                    'agent_type', 'risk_manager_agent',
                    'node_category', 'agent',
                    'config', jsonb_build_object(
                        'agent_id', 'risk-1',
                        'agent_type', 'risk_manager_agent',
                        'max_position_size_pct', 25,
                        'max_risk_per_trade_pct', 2,
                        'min_risk_reward_ratio', 1.5,
                        'instructions', 'Validate trade setup. Maximum position size: 25% of account. Maximum risk per trade: 2%. Minimum risk/reward: 1.5:1. Reject trades that exceed these limits.'
                    )
                )
            ),
            'edges', jsonb_build_array(
                jsonb_build_object('from', 'node-1', 'to', 'node-2'),
                jsonb_build_object('from', 'node-2', 'to', 'node-3'),
                jsonb_build_object('from', 'node-3', 'to', 'node-4'),
                jsonb_build_object('from', 'node-4', 'to', 'node-5')
            )
        ),
        scanner_id_var,
        true,
        NOW(),
        NOW(),
        'signal'::triggermode
    )
    ON CONFLICT DO NOTHING;
    
    RAISE NOTICE 'Forex scanner and pipeline created successfully!';
    RAISE NOTICE 'Scanner ID: %', scanner_id_var;
    RAISE NOTICE 'Scanner Tickers: EUR_USD, GBP_USD, USD_JPY, USD_CHF, AUD_USD, NZD_USD';
END $$;

-- 4. Verify the setup
SELECT 
    p.id as pipeline_id,
    p.name as pipeline_name,
    s.id as scanner_id,
    s.name as scanner_name,
    s.config->'tickers' as tickers
FROM pipelines p
JOIN scanners s ON p.scanner_id = s.id
WHERE s.name = 'Forex Major Pairs';
