"""
Telegram Notification Service

Sends notifications to users via their own Telegram bots.
Users create their own bot via @BotFather and configure it in settings.
"""
import requests
import structlog
from typing import Optional, Dict, Any

logger = structlog.get_logger()


class TelegramNotifier:
    """
    Send notifications via Telegram Bot API.
    
    Users provide their own bot token and chat ID.
    Free forever, no rate limits (respects Telegram API limits).
    """
    
    BASE_URL = "https://api.telegram.org"
    
    @staticmethod
    def send_message(
        bot_token: str,
        chat_id: str,
        message: str,
        parse_mode: str = "Markdown"
    ) -> Dict[str, Any]:
        """
        Send a Telegram message.
        
        Args:
            bot_token: User's bot token from @BotFather
            chat_id: User's Telegram chat ID
            message: Message text (supports Markdown or HTML)
            parse_mode: "Markdown" or "HTML" formatting
            
        Returns:
            Dict with status and response data
        """
        url = f"{TelegramNotifier.BASE_URL}/bot{bot_token}/sendMessage"
        
        try:
            response = requests.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": parse_mode
                },
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info("telegram_sent", chat_id=chat_id[:5] + "***")
                return {
                    "status": "sent",
                    "channel": "telegram",
                    "message_id": response.json().get("result", {}).get("message_id")
                }
            else:
                error_data = response.json()
                error_msg = error_data.get("description", response.text)
                logger.error(
                    "telegram_failed",
                    status=response.status_code,
                    error=error_msg
                )
                return {
                    "status": "error",
                    "message": error_msg,
                    "code": response.status_code
                }
                
        except requests.exceptions.Timeout:
            logger.error("telegram_timeout")
            return {"status": "error", "message": "Request timeout"}
        except Exception as e:
            logger.error("telegram_exception", error=str(e))
            return {"status": "error", "message": str(e)}
    
    @staticmethod
    def send_trade_alert(
        bot_token: str,
        chat_id: str,
        symbol: str,
        action: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        position_size: float,
        pipeline_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send trade execution alert.
        
        Args:
            bot_token: User's bot token
            chat_id: User's chat ID
            symbol: Trading symbol
            action: BUY or SELL
            entry_price: Entry price
            stop_loss: Stop loss price
            take_profit: Take profit price
            position_size: Position size
            pipeline_name: Optional pipeline name
            
        Returns:
            Dict with status
        """
        emoji = "🟢" if action.upper() == "BUY" else "🔴"
        pipeline_info = f"\n📋 Pipeline: `{pipeline_name}`" if pipeline_name else ""
        
        message = f"""{emoji} *Trade Executed*{pipeline_info}

📊 Symbol: `{symbol}`
🎯 Action: *{action.upper()}*
💰 Entry: ${entry_price:.2f}
🛑 Stop Loss: ${stop_loss:.2f}
🎉 Take Profit: ${take_profit:.2f}
📦 Size: {position_size} units

Good luck! 🚀"""
        
        return TelegramNotifier.send_message(bot_token, chat_id, message)
    
    @staticmethod
    def send_position_closed(
        bot_token: str,
        chat_id: str,
        symbol: str,
        pnl: float,
        pnl_percent: float,
        exit_reason: str,
        pipeline_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send position closed alert.
        
        Args:
            bot_token: User's bot token
            chat_id: User's chat ID
            symbol: Trading symbol
            pnl: Profit/Loss in dollars
            pnl_percent: P&L percentage
            exit_reason: Reason for exit (TP hit, SL hit, manual, etc.)
            pipeline_name: Optional pipeline name
            
        Returns:
            Dict with status
        """
        emoji = "🎉" if pnl >= 0 else "😔"
        result_emoji = "✅" if pnl >= 0 else "❌"
        pipeline_info = f"\n📋 Pipeline: `{pipeline_name}`" if pipeline_name else ""
        
        message = f"""{emoji} *Position Closed*{pipeline_info}

📊 Symbol: `{symbol}`
{result_emoji} P&L: ${pnl:.2f} ({pnl_percent:+.2f}%)
🏁 Reason: {exit_reason}

{"Well done! 🎯" if pnl >= 0 else "Better luck next time! 💪"}"""
        
        return TelegramNotifier.send_message(bot_token, chat_id, message)
    
    @staticmethod
    def send_risk_rejection(
        bot_token: str,
        chat_id: str,
        symbol: str,
        reason: str,
        pipeline_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send risk manager rejection alert.
        
        Args:
            bot_token: User's bot token
            chat_id: User's chat ID
            symbol: Trading symbol
            reason: Rejection reason
            pipeline_name: Optional pipeline name
            
        Returns:
            Dict with status
        """
        pipeline_info = f"\n📋 Pipeline: `{pipeline_name}`" if pipeline_name else ""
        
        message = f"""⚠️ *Trade Rejected by Risk Manager*{pipeline_info}

📊 Symbol: `{symbol}`
🚫 Reason: {reason}

Your capital is protected! 🛡️"""
        
        return TelegramNotifier.send_message(bot_token, chat_id, message)
    
    @staticmethod
    def send_pipeline_error(
        bot_token: str,
        chat_id: str,
        pipeline_name: str,
        error_message: str,
        symbol: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send pipeline failure alert.
        
        Args:
            bot_token: User's bot token
            chat_id: User's chat ID
            pipeline_name: Pipeline name
            error_message: Error description
            symbol: Optional trading symbol
            
        Returns:
            Dict with status
        """
        symbol_info = f"\n📊 Symbol: `{symbol}`" if symbol else ""
        
        message = f"""❌ *Pipeline Failed*

📋 Pipeline: `{pipeline_name}`{symbol_info}
⚠️ Error: {error_message}

Please check your pipeline configuration."""
        
        return TelegramNotifier.send_message(bot_token, chat_id, message)
    
    @staticmethod
    def send_test_message(
        bot_token: str,
        chat_id: str
    ) -> Dict[str, Any]:
        """
        Send a test message to verify Telegram setup.
        
        Args:
            bot_token: User's bot token
            chat_id: User's chat ID
            
        Returns:
            Dict with status
        """
        message = """✅ *Telegram Connected Successfully!*

Your trading platform is now ready to send notifications.

You'll receive alerts for:
• Trade executions
• Position closures
• Risk rejections
• Pipeline errors

Happy trading! 🚀"""
        
        return TelegramNotifier.send_message(bot_token, chat_id, message)


# Singleton instance
telegram_notifier = TelegramNotifier()
