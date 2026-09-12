"""
Lab #3: Baseline Chatbot vs ReAct Agent
Học viên hoàn thiện các mục TODO để hoàn thành bài lab.
"""

import json
from tools import TOOL_DEFINITIONS, TOOL_MAP, get_flight_info, get_weather_forecast

SYSTEM_PROMPT = """Bạn là một ReAct Agent thông minh hỗ trợ khách hàng Vingroup.
Bạn chỉ sử dụng các công cụ sau:
{tools}

Quy trình trả lời bắt buộc:
Thought: <Suy nghĩ bước tiếp theo>
Action: {{"name": "<tên tool>", "args": {{<tham số>}}}}
Observation: <Kết quả từ tool>
... (Lặp lại cho tới khi có đủ dữ liệu)
Final Answer: <Câu trả lời hoàn chỉnh cho khách hàng>
"""

class ChatbotBaseline:
    """Baseline LLM Chatbot (Không sử dụng ReAct Loop hay Tools)"""
    def query(self, user_input: str) -> str:
        # TODO: Trả về câu trả lời tĩnh hoặc gọi LLM 1 lượt (không dùng tool)
        return {
            "status": "success",
            "tool_calls": [],
            "answer": (
                "Xin lỗi, tôi không có kết nối cơ sở dữ liệu nên không tra cứu được "
                f"thông tin chuyến bay hay thời tiết cho câu hỏi: {user_input}"
            ),
        }

class ReActAgent:
    """ReAct Agent có sử dụng Thought-Action-Observation Loop"""
    def __init__(self, max_iterations: int = 5):
        self.max_iterations = max_iterations
        self.trace = []

    def run(self, user_input: str) -> str:
        # TODO 1: Khởi tạo mảng lưu lịch sử conversation / traces
        self.trace = []
        observations = []
        pending_actions = self._decide_actions(user_input)
        needs_separate_final = len(pending_actions) > 1
        iteration = 0

        # TODO 2: Thiết lập vòng lặp while iteration < self.max_iterations
        while iteration < self.max_iterations:
            iteration += 1

            # TODO 3: Phân tích Thought / Action từ Agent
            if pending_actions:
                action = pending_actions.pop(0)
                thought = self._thought_for_action(action)
                action_payload = {"name": action["name"], "args": action["args"]}
                try:
                    parsed = json.loads(json.dumps(action_payload))
                    tool_name = str(parsed.get("name", "")).strip().lower()
                    args = parsed.get("args", {})
                    if not isinstance(args, dict):
                        raise json.JSONDecodeError("args must be object", str(args), 0)
                except (json.JSONDecodeError, TypeError, ValueError):
                    observation = "Invalid JSON format"
                else:
                    # TODO 4: Thực thi Tool trong TOOL_MAP nếu có Action
                    tool_fn = TOOL_MAP.get(tool_name)
                    if tool_fn is None:
                        observation = f"Unknown tool: {tool_name}"
                    else:
                        observation = tool_fn(**args)

                # TODO 5: Ghi lại Observation và lặp lại cho tới khi ra Final Answer
                observations.append(observation)
                self.trace.append({
                    "iteration": iteration,
                    "thought": thought,
                    "action": action_payload,
                    "observation": observation,
                })

                if not pending_actions and not needs_separate_final:
                    answer = self._compose_answer(user_input, observations)
                    return {
                        "status": "completed",
                        "iterations": iteration,
                        "answer": answer,
                        "trace": self.trace,
                    }
                continue

            thought = "Tôi đã thu thập đủ thông tin để trả lời khách hàng."
            answer = self._compose_answer(user_input, observations)
            self.trace.append({
                "iteration": iteration,
                "thought": thought,
                "final_answer": answer,
            })
            return {
                "status": "completed",
                "iterations": iteration,
                "answer": answer,
                "trace": self.trace,
            }

        return {
            "status": "max_iterations_reached",
            "answer": "Không thể hoàn thành trong số bước tối đa.",
            "trace": self.trace,
            "iterations": iteration,
        }

    def _extract_airports(self, user_input: str):
        upper = user_input.upper()
        found = []
        i = 0
        while i < len(upper):
            matched = None
            for code in ("HAN", "SGN", "DAD"):
                if upper.startswith(code, i):
                    matched = code
                    break
            if matched:
                found.append(matched)
                i += len(matched)
            else:
                i += 1
        return found

    def _extract_max_price(self, user_input: str) -> int:
        text = user_input.lower().replace(",", ".")
        if "triệu" in text:
            chunk = text.split("triệu")[0].strip().split()[-1]
            try:
                return int(float(chunk) * 1_000_000)
            except ValueError:
                pass
        return 5_000_000

    def _thought_for_action(self, action: dict) -> str:
        name = action["name"]
        args = action.get("args", {})
        if name == "get_weather_forecast":
            return f"Tôi cần kiểm tra thông tin thời tiết tại {args.get('city_code')}."
        origin = args.get("origin")
        destination = args.get("destination")
        return f"Tôi cần tìm chuyến bay từ {origin} đi {destination}."

    def _decide_actions(self, user_input: str):
        lower = user_input.lower()
        if "vinpearl" in lower or "chính sách" in lower:
            return []

        airports = self._extract_airports(user_input)
        actions = []
        need_flight = any(k in lower for k in ["chuyến bay", "vé"])
        need_weather = any(k in lower for k in ["thời tiết", "mặc"])

        if need_flight:
            origin = airports[0] if airports else "HAN"
            destination = airports[1] if len(airports) > 1 else origin
            actions.append({
                "name": "get_flight_info",
                "args": {
                    "origin": origin,
                    "destination": destination,
                    "max_price": self._extract_max_price(user_input),
                },
            })
        if need_weather:
            city_code = airports[-1] if airports else "SGN"
            actions.append({
                "name": "get_weather_forecast",
                "args": {"city_code": city_code},
            })
        return actions

    def _compose_answer(self, user_input: str, observations) -> str:
        if not observations:
            return (
                "Chính sách đổi trả vé máy bay Vinpearl: quý khách có thể đổi hoặc trả vé "
                "trước giờ bay theo điều kiện và phí do Vinpearl quy định."
            )

        flights = []
        weather = None
        extras = []
        for obs in observations:
            if isinstance(obs, list):
                flights.extend(obs)
            elif isinstance(obs, dict) and obs.get("error"):
                extras.append(str(obs["error"]))
            elif isinstance(obs, dict) and "city" in obs:
                weather = obs
            elif obs is not None:
                extras.append(str(obs))

        sections = []
        section_no = 1
        if flights:
            lines = [f"{section_no}. Thông tin chuyến bay:"]
            for fl in flights:
                lines.append(
                    f"  - {fl['airline']} ({fl['flight_number']}): {fl['departure_time']} - Giá: {fl['price_vnd']:,} VNĐ"
                )
            sections.append("\n".join(lines))
            section_no += 1
        if weather:
            sections.append(
                f"{section_no}. Thông tin thời tiết & trang phục:\n"
                f"  - Thời tiết tại {weather.get('city')}: {weather.get('temperature_c')}°C ({weather.get('condition')}).\n"
                f"  - Gợi ý trang phục: {weather.get('recommendation')}"
            )
            section_no += 1
        if extras:
            sections.append(" ".join(extras))
        return "\n".join(sections)

def main():
    user_query = "Tìm cho tôi chuyến bay từ HAN đi SGN dưới 2 triệu, rồi cho biết thời tiết SGN nên mặc gì?"
    
    print("=== RUNNING CHATBOT BASELINE ===")
    chatbot = ChatbotBaseline()
    print(chatbot.query(user_query))
    
    print("\n=== RUNNING REACT AGENT ===")
    agent = ReActAgent(max_iterations=5)
    result = agent.run(user_query)
    print("Result:", result)
    print("Trace Log:", json.dumps(agent.trace, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()