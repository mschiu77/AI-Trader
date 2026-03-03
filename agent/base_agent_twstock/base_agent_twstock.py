"""
TW Stock Base Agent Class
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

# Import custom DeepSeek wrapper if needed (reusing from AStock or defining here)
# For simplicity, let's redefine it here to be self-contained or import if it was in a common place.
# Since it was defined inside base_agent_astock.py, I will copy it here.

class DeepSeekChatOpenAI(ChatOpenAI):
    """
    Custom ChatOpenAI wrapper for DeepSeek API compatibility.
    Handles the case where DeepSeek returns tool_calls.args as JSON strings instead of dicts.
    """

    def _create_message_dicts(self, messages: list, stop: Optional[list] = None) -> list:
        """Override to handle response parsing"""
        message_dicts = super()._create_message_dicts(messages, stop)
        return message_dicts

    def _generate(self, messages: list, stop: Optional[list] = None, **kwargs):
        """Override generation to fix tool_calls format in responses"""
        # Call parent's generate method
        result = super()._generate(messages, stop, **kwargs)

        # Fix tool_calls format in the generated messages
        for generation in result.generations:
            for gen in generation:
                if hasattr(gen, "message") and hasattr(gen.message, "additional_kwargs"):
                    tool_calls = gen.message.additional_kwargs.get("tool_calls")
                    if tool_calls:
                        for tool_call in tool_calls:
                            if "function" in tool_call and "arguments" in tool_call["function"]:
                                args = tool_call["function"]["arguments"]
                                # If arguments is a string, parse it
                                if isinstance(args, str):
                                    try:
                                        tool_call["function"]["arguments"] = json.loads(args)
                                    except json.JSONDecodeError:
                                        pass  # Keep as string if parsing fails

        return result

    async def _agenerate(self, messages: list, stop: Optional[list] = None, **kwargs):
        """Override async generation to fix tool_calls format in responses"""
        # Call parent's async generate method
        result = await super()._agenerate(messages, stop, **kwargs)

        # Fix tool_calls format in the generated messages
        for generation in result.generations:
            for gen in generation:
                if hasattr(gen, "message") and hasattr(gen.message, "additional_kwargs"):
                    tool_calls = gen.message.additional_kwargs.get("tool_calls")
                    if tool_calls:
                        for tool_call in tool_calls:
                            if "function" in tool_call and "arguments" in tool_call["function"]:
                                args = tool_call["function"]["arguments"]
                                # If arguments is a string, parse it
                                if isinstance(args, str):
                                    try:
                                        tool_call["function"]["arguments"] = json.loads(args)
                                    except json.JSONDecodeError:
                                        pass  # Keep as string if parsing fails

        return result


from prompts.agent_prompt_twstock import STOP_SIGNAL, get_agent_system_prompt_twstock
from tools.general_tools import extract_conversation, extract_tool_messages, get_config_value, write_config_value
from tools.price_tools import add_no_trade_record, is_trading_day

# Import TW50 symbols
try:
    from data.TW_stock.get_daily_price_tw import tw_50_codes
except ImportError:
    tw_50_codes = ["2330.TW", "2317.TW", "2454.TW", "2308.TW", "2881.TW"]

load_dotenv()


class BaseAgentTWStock:
    """
    TW Stock Trading Agent Base Class
    """

    def __init__(
        self,
        signature: str,
        basemodel: str,
        stock_symbols: Optional[List[str]] = None,
        mcp_config: Optional[Dict[str, Dict[str, Any]]] = None,
        log_path: Optional[str] = None,
        max_steps: int = 10,
        max_retries: int = 3,
        base_delay: float = 0.5,
        openai_base_url: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        initial_cash: float = 1000000.0,  # Default 1M TWD
        init_date: str = "2025-10-01",
        market: str = "tw",  # Accepted but ignored, always uses "tw"
    ):
        self.signature = signature
        self.basemodel = basemodel
        self.market = "tw"

        # Default to TW50 symbols
        if stock_symbols is None:
            self.stock_symbols = tw_50_codes
        else:
            self.stock_symbols = stock_symbols

        self.max_steps = max_steps
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.initial_cash = initial_cash
        self.init_date = init_date

        # Set MCP configuration
        self.mcp_config = mcp_config or self._get_default_mcp_config()

        # Set log path
        self.base_log_path = log_path or "./data/agent_data_twstock"

        # Set OpenAI configuration
        if openai_base_url is None:
            self.openai_base_url = os.getenv("OPENAI_API_BASE")
        else:
            self.openai_base_url = openai_base_url
        if openai_api_key is None:
            self.openai_api_key = os.getenv("OPENAI_API_KEY")
        else:
            self.openai_api_key = openai_api_key

        # Initialize components
        self.client: Optional[MultiServerMCPClient] = None
        self.tools: Optional[List] = None
        self.model: Optional[ChatOpenAI] = None
        self.agent: Optional[Any] = None

        # Data paths
        self.data_path = os.path.join(self.base_log_path, self.signature)
        self.position_file = os.path.join(self.data_path, "position", "position.jsonl")

    def _get_default_mcp_config(self) -> Dict[str, Dict[str, Any]]:
        """Get default MCP configuration"""
        return {
            "math": {
                "transport": "streamable_http",
                "url": f"http://localhost:{os.getenv('MATH_HTTP_PORT', '8000')}/mcp",
            },
            "stock_local": {
                "transport": "streamable_http",
                "url": f"http://localhost:{os.getenv('GETPRICE_HTTP_PORT', '8003')}/mcp",
            },
            "search": {
                "transport": "streamable_http",
                "url": f"http://localhost:{os.getenv('SEARCH_HTTP_PORT', '8004')}/mcp",
            },
            "trade": {
                "transport": "streamable_http",
                "url": f"http://localhost:{os.getenv('TRADE_HTTP_PORT', '8002')}/mcp",
            },
        }

    async def initialize(self) -> None:
        """Initialize MCP client and AI model"""
        print(f"🚀 Initializing TW Stock agent: {self.signature}")

        if not self.openai_api_key:
            raise ValueError(
                "❌ OpenAI API key not set. Please configure OPENAI_API_KEY in environment or config file."
            )

        try:
            self.client = MultiServerMCPClient(self.mcp_config)
            self.tools = await self.client.get_tools()
            if not self.tools:
                print("⚠️  Warning: No MCP tools loaded.")
            else:
                print(f"✅ Loaded {len(self.tools)} MCP tools")
        except Exception as e:
            raise RuntimeError(f"❌ Failed to initialize MCP client: {e}")

        try:
            if "deepseek" in self.basemodel.lower():
                self.model = DeepSeekChatOpenAI(
                    model=self.basemodel,
                    base_url=self.openai_base_url,
                    api_key=self.openai_api_key,
                    max_retries=3,
                    timeout=30,
                )
            else:
                self.model = ChatOpenAI(
                    model=self.basemodel,
                    base_url=self.openai_base_url,
                    api_key=self.openai_api_key,
                    max_retries=3,
                    timeout=30,
                )
        except Exception as e:
            raise RuntimeError(f"❌ Failed to initialize AI model: {e}")

        print(f"✅ TW Stock agent {self.signature} initialization completed")

    def _setup_logging(self, today_date: str) -> str:
        """Set up log file path"""
        log_path = os.path.join(self.base_log_path, self.signature, "log", today_date)
        if not os.path.exists(log_path):
            os.makedirs(log_path)
        return os.path.join(log_path, "log.jsonl")

    def _log_message(self, log_file: str, new_messages: List[Dict[str, str]]) -> None:
        """Log messages to log file"""
        log_entry = {"timestamp": datetime.now().isoformat(), "signature": self.signature, "new_messages": new_messages}
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    async def _ainvoke_with_retry(self, message: List[Dict[str, str]]) -> Any:
        """Agent invocation with retry"""
        for attempt in range(1, self.max_retries + 1):
            try:
                return await self.agent.ainvoke({"messages": message}, {"recursion_limit": 100})
            except Exception as e:
                if attempt == self.max_retries:
                    raise e
                print(f"⚠️ Attempt {attempt} failed, retrying after {self.base_delay * attempt} seconds...")
                await asyncio.sleep(self.base_delay * attempt)

    async def run_trading_session(self, today_date: str) -> None:
        """Run single day trading session"""
        print(f"📈 Starting TW Stock trading session: {today_date}")
        log_file = self._setup_logging(today_date)

        self.agent = create_agent(
            self.model,
            tools=self.tools,
            system_prompt=get_agent_system_prompt_twstock(today_date, self.signature, self.stock_symbols),
        )

        user_query = [{"role": "user", "content": f"Please analyze and update positions for today ({today_date})."}]
        message = user_query.copy()
        self._log_message(log_file, user_query)

        current_step = 0
        while current_step < self.max_steps:
            current_step += 1
            print(f"🔄 Step {current_step}/{self.max_steps}")

            try:
                response = await self._ainvoke_with_retry(message)
                agent_response = extract_conversation(response, "final")

                if STOP_SIGNAL in agent_response:
                    print("✅ Received stop signal, trading session ended")
                    self._log_message(log_file, [{"role": "assistant", "content": agent_response}])
                    break

                tool_msgs = extract_tool_messages(response)
                tool_response = "\n".join([msg.content for msg in tool_msgs])

                new_messages = [
                    {"role": "assistant", "content": agent_response},
                    {"role": "user", "content": f"Tool results: {tool_response}"},
                ]
                message.extend(new_messages)
                self._log_message(log_file, new_messages[0])
                self._log_message(log_file, new_messages[1])

            except Exception as e:
                print(f"❌ Trading session error: {str(e)}")
                raise

        await self._handle_trading_result(today_date)

    async def _handle_trading_result(self, today_date: str) -> None:
        """Handle trading results"""
        if_trade = get_config_value("IF_TRADE")
        if if_trade:
            write_config_value("IF_TRADE", False)
            print("✅ Trading completed")
        else:
            print("📊 No trading, maintaining positions")
            try:
                add_no_trade_record(today_date, self.signature)
            except NameError as e:
                print(f"❌ NameError: {e}")
                raise
            write_config_value("IF_TRADE", False)

    def register_agent(self) -> None:
        """Register new agent, create initial positions"""
        if os.path.exists(self.position_file):
            print(f"⚠️ Position file {self.position_file} already exists, skipping registration")
            return

        position_dir = os.path.join(self.data_path, "position")
        if not os.path.exists(position_dir):
            os.makedirs(position_dir)
            print(f"📁 Created position directory: {position_dir}")

        init_position = {symbol: 0 for symbol in self.stock_symbols}
        init_position["CASH"] = self.initial_cash
        
        # Normalize init_date
        init_date_str = self.init_date
        if " " in init_date_str:
            try:
                # If already proper format, keep it
                datetime.strptime(init_date_str, "%Y-%m-%d %H:%M:%S")
            except Exception:
                try:
                    date_part, time_part = init_date_str.split(" ", 1)
                    hh, mm, ss = time_part.split(":")
                    init_date_str = f"{date_part} {hh.zfill(2)}:{mm}:{ss}"
                except Exception:
                    pass

        with open(self.position_file, "w") as f:
            f.write(json.dumps({"date": init_date_str, "id": 0, "positions": init_position}) + "\n")

        print(f"✅ TW Stock agent {self.signature} registration completed")
        print(f"💰 Initial cash: {self.initial_cash:,.2f}")

    def get_trading_dates(self, init_date: str, end_date: str) -> List[str]:
        """Get trading date list"""
        dates = []
        max_date = None

        if not os.path.exists(self.position_file):
            self.register_agent()
            max_date = init_date
        else:
            with open(self.position_file, "r") as f:
                for line in f:
                    doc = json.loads(line)
                    current_date = doc["date"]
                    if max_date is None:
                        max_date = current_date
                    else:
                        current_date_obj = datetime.strptime(current_date, "%Y-%m-%d")
                        max_date_obj = datetime.strptime(max_date, "%Y-%m-%d")
                        if current_date_obj > max_date_obj:
                            max_date = current_date

        max_date_obj = datetime.strptime(max_date, "%Y-%m-%d")
        end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")

        if end_date_obj <= max_date_obj:
            return []

        trading_dates = []
        current_date = max_date_obj + timedelta(days=1)

        while current_date <= end_date_obj:
            date_str = current_date.strftime("%Y-%m-%d")
            # is_trading_day uses get_merged_file_path(market) internally
            if is_trading_day(date_str, market="tw"):
                trading_dates.append(date_str)
            current_date += timedelta(days=1)

        return trading_dates

    async def run_with_retry(self, today_date: str) -> None:
        """Run method with retry"""
        for attempt in range(1, self.max_retries + 1):
            try:
                print(f"🔄 Attempting to run {self.signature} - {today_date} (Attempt {attempt})")
                await self.run_trading_session(today_date)
                print(f"✅ {self.signature} - {today_date} run successful")
                return
            except Exception as e:
                print(f"❌ Attempt {attempt} failed: {str(e)}")
                if attempt == self.max_retries:
                    raise
                else:
                    await asyncio.sleep(self.base_delay * attempt)

    async def run_date_range(self, init_date: str, end_date: str) -> None:
        """Run all trading days in date range"""
        print(f"📅 Running TW Stock date range: {init_date} to {end_date}")

        trading_dates = self.get_trading_dates(init_date, end_date)

        if not trading_dates:
            print(f"ℹ️ No trading days to process")
            return

        print(f"📊 Trading days to process: {trading_dates}")

        for date in trading_dates:
            print(f"🔄 Processing {self.signature} - Date: {date}")
            write_config_value("TODAY_DATE", date)
            write_config_value("SIGNATURE", self.signature)
            write_config_value("MARKET", "tw")  # Ensure market is set to tw

            try:
                await self.run_with_retry(date)
            except Exception as e:
                print(f"❌ Error processing {self.signature} - Date: {date}")
                print(e)
                # Continue? or raise? Usually raise to stop
                raise

        print(f"✅ {self.signature} processing completed")

    def get_position_summary(self) -> Dict[str, Any]:
        """Get position summary"""
        if not os.path.exists(self.position_file):
            return {"error": "Position file does not exist"}

        positions = []
        with open(self.position_file, "r") as f:
            for line in f:
                positions.append(json.loads(line))

        if not positions:
            return {"error": "No position records"}

        latest_position = positions[-1]
        return {
            "signature": self.signature,
            "latest_date": latest_position.get("date"),
            "positions": latest_position.get("positions", {}),
            "total_records": len(positions),
        }
