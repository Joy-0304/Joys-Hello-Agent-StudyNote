import requests
import json
import os
import re
from tavily import TavilyClient
from openai import OpenAI

# ===================== 配置项 =====================
YOUR_TAVILY_API_KEY = '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'
YOUR_API_KEY = 'ms-224c703a-c76d-4c06-8f59-810b1fefdd14'
os.environ['TAVILY_API_KEY'] = YOUR_TAVILY_API_KEY

# ===================== 1. 用户偏好记忆类 =====================
class UserPreference:
    def __init__(self):
        # 显式偏好（用户直接输入）
        self.explicit_preferences = {
            "attraction_type": None,  # 如"历史文化"、"自然景观"
            "budget_range": None,     # 如"0-500"、"500-1000"
            "avoid_crowded": None,    # True/False
            "ticket_price": None      # 心理价位
        }
        # 隐式偏好（从行为推断）
        self.implicit_preferences = {
            "rejected_attraction_types": [],  # 被拒绝的景点类型
            "rejected_reasons": []            # 拒绝原因（如"太贵"、"人多"）
        }
        # 拒绝计数器
        self.reject_count = 0

    def update_explicit(self, key, value):
        """更新显式偏好"""
        if key in self.explicit_preferences:
            self.explicit_preferences[key] = value

    def update_implicit(self, reject_type=None, reject_reason=None):
        """更新隐式偏好（记录拒绝行为）"""
        if reject_type and reject_type not in self.implicit_preferences["rejected_attraction_types"]:
            self.implicit_preferences["rejected_attraction_types"].append(reject_type)
        if reject_reason and reject_reason not in self.implicit_preferences["rejected_reasons"]:
            self.implicit_preferences["rejected_reasons"].append(reject_reason)
        if reject_type or reject_reason:
            self.reject_count += 1  # 拒绝次数+1

    def get_preferences_str(self):
        """将偏好转为字符串，供LLM参考"""
        explicit = [f"{k}: {v}" for k, v in self.explicit_preferences.items() if v]
        implicit = [
            f"拒绝过的景点类型: {', '.join(self.implicit_preferences['rejected_attraction_types']) if self.implicit_preferences['rejected_attraction_types'] else '无'}",
            f"拒绝原因: {', '.join(self.implicit_preferences['rejected_reasons']) if self.implicit_preferences['rejected_reasons'] else '无'}",
            f"连续拒绝次数: {self.reject_count}"
        ]
        return "用户偏好：\n- " + "\n- ".join(explicit + implicit)

    def reset_reject_count(self):
        """重置拒绝计数器"""
        self.reject_count = 0

# ===================== 2. 扩展系统提示词 =====================
AGENT_SYSTEM_PROMPT = """
你是一个智能旅行助手。你的任务是分析用户的请求，并使用可用工具一步步地解决问题。

# 核心能力：
1. 记忆用户偏好：主动识别并记录用户的显式/隐式偏好（景点类型、预算、禁忌等）；
2. 门票售罄处理：若推荐景点门票售罄，自动推荐备选方案；
3. 反思调整：若用户连续明确拒绝3次推荐或者没有接受方案，分析拒绝原因并调整推荐策略。
4. 人性化表达：当用户表示想要了解其他方案时，不要重复推荐；当用户表现出感谢或者结束话题的意向时，表达这是自己的职责并祝用户旅途愉快。

# 可用工具:
- `get_weather(city: str)`: 查询指定城市的实时天气。
- `get_attraction(city: str, weather: str, preferences: str)`: 根据城市、天气和用户偏好推荐旅游景点（preferences传入用户偏好字符串）。
- `check_ticket_availability(attraction: str, city: str)`: 查询指定景点的门票是否可售。
- `get_alternative_attractions(city: str, weather: str, rejected_type: str, preferences: str)`: 推荐备选景点（rejected_type为被拒绝的景点类型）。
- `extract_preferences(user_input: str)`: 从用户输入中提取显式偏好（如"预算500以内"、"喜欢历史景点"）。

# 行动格式:
你的回答必须严格遵循以下格式，每次回复只输出一对Thought-Action：
Thought: [这里是你的思考过程和下一步计划，需结合用户偏好、拒绝次数等信息]
Action: [这里是你要调用的工具，格式为 function_name(arg_name="arg_value")]

# 规则：
1. 首次交互优先调用extract_preferences提取用户显式偏好；
2. 推荐景点前必须先调用check_ticket_availability验证门票状态；
3. 若门票售罄，立即调用get_alternative_attractions推荐备选；
4. 若用户连续拒绝≥3次，需分析拒绝原因（如预算/类型），调整preferences参数重新推荐；
5. 当收集到足够信息，使用 finish(answer="...") 输出最终答案，需包含用户偏好适配、门票状态、推荐理由。

请开始吧！
"""

# ===================== 3. 扩展工具函数 =====================
# 工具1：查询天气（原有，无修改）
def get_weather(city: str) -> str:
    url = f"https://wttr.in/{city}?format=j1"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        current_condition = data['current_condition'][0]
        weather_desc = current_condition['weatherDesc'][0]['value']
        temp_c = current_condition['temp_C']
        return f"{city}当前天气:{weather_desc}，气温{temp_c}摄氏度"
    except requests.exceptions.RequestException as e:
        return f"错误:查询天气时遇到网络问题 - {e}"
    except (KeyError, IndexError) as e:
        return f"错误:解析天气数据失败，可能是城市名称无效 - {e}"

# 工具2：提取用户偏好（新增）
def extract_preferences(user_input: str) -> str:
    """从用户输入中提取显式偏好，返回结构化字符串"""
    preferences = {}
    # 匹配景点类型
    type_patterns = {
        "历史文化": ["历史", "文化", "古迹", "博物馆", "故宫", "长城"],
        "自然景观": ["自然", "山水", "公园", "湖泊", "森林", "海边"],
        "娱乐休闲": ["娱乐", "休闲", "乐园", "购物", "美食"]
    }
    for attr_type, keywords in type_patterns.items():
        if any(keyword in user_input for keyword in keywords):
            preferences["attraction_type"] = attr_type
            break
    # 匹配预算
    budget_match = re.search(r"预算(\d+)-?(\d+)?", user_input)
    if budget_match:
        min_b = budget_match.group(1)
        max_b = budget_match.group(2) if budget_match.group(2) else "不限"
        preferences["budget_range"] = f"{min_b}-{max_b}"
    # 匹配是否避拥挤
    if any(kw in user_input for kw in ["人少", "不拥挤", "小众"]):
        preferences["avoid_crowded"] = "是"
    if not preferences:
        return "未提取到明确偏好，默认推荐综合类景点"
    return "; ".join([f"{k}: {v}" for k, v in preferences.items()])

# 工具3：检查门票可用性（新增）
def check_ticket_availability(attraction: str, city: str) -> str:
    """模拟查询门票状态（实际可对接票务API）"""
    # 模拟售罄景点列表（可替换为真实接口）
    sold_out_attractions = {
        "上海": ["上海迪士尼乐园", "豫园"],
        "北京": ["故宫博物院", "八达岭长城"]
    }
    if city in sold_out_attractions and attraction in sold_out_attractions[city]:
        return f"{attraction}（{city}）门票已售罄"
    else:
        return f"{attraction}（{city}）门票可正常购买"

# 工具4：推荐景点（扩展，增加偏好参数）
def get_attraction(city: str, weather: str, preferences: str) -> str:
    api_key = YOUR_TAVILY_API_KEY
    if not api_key:
        return "错误:未配置TAVILY_API_KEY环境变量。"
    tavily = TavilyClient(api_key=api_key)
    # 结合天气+偏好构造查询
    query = f"{city} {weather}天气下，{preferences}的旅游景点推荐及理由"
    try:
        response = tavily.search(query=query, search_depth="basic", include_answer=True)
        if response.get("answer"):
            return response["answer"]
        formatted_results = []
        for result in response.get("results", []):
            formatted_results.append(f"- {result['title']}: {result['content'][:100]}...")
        return "根据搜索，为您推荐:\n" + "\n".join(formatted_results) if formatted_results else "暂无推荐"
    except Exception as e:
        return f"错误:搜索景点失败 - {e}"

# 工具5：推荐备选景点（新增）
def get_alternative_attractions(city: str, weather: str, rejected_type: str, preferences: str) -> str:
    api_key = YOUR_TAVILY_API_KEY
    if not api_key:
        return "错误:未配置TAVILY_API_KEY环境变量。"
    tavily = TavilyClient(api_key=api_key)
    query = f"{city} {weather}天气下，替代{rejected_type}的景点推荐（{preferences}）及理由"
    try:
        response = tavily.search(query=query, search_depth="basic", include_answer=True)
        if response.get("answer"):
            return response["answer"]
        formatted_results = []
        for result in response.get("results", []):
            formatted_results.append(f"- {result['title']}: {result['content'][:100]}...")
        return "为您推荐备选景点:\n" + "\n".join(formatted_results) if formatted_results else "暂无备选"
    except Exception as e:
        return f"错误:搜索备选景点失败 - {e}"

# 工具字典（整合新增/扩展工具）
available_tools = {
    "get_weather": get_weather,
    "extract_preferences": extract_preferences,
    "check_ticket_availability": check_ticket_availability,
    "get_attraction": get_attraction,
    "get_alternative_attractions": get_alternative_attractions
}

# ===================== 4. LLM客户端（原有，无修改） =====================
class OpenAICompatibleClient:
    def __init__(self, model: str, api_key: str, base_url: str):
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def generate(self, prompt: str, system_prompt: str) -> str:
        print("正在调用大语言模型...")
        try:
            messages = [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': prompt}
            ]
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=False
            )
            answer = response.choices[0].message.content
            print("大语言模型响应成功。")
            return answer
        except Exception as e:
            print(f"调用LLM API时发生错误: {e}")
            return "错误:调用语言模型服务时出错。"

# ===================== 5. 命令行交互主逻辑 =====================
def run_agent_interaction():
    # 初始化LLM客户端
    llm = OpenAICompatibleClient(
        model='Qwen/Qwen3-Next-80B-A3B-Instruct',
        api_key=YOUR_API_KEY,
        base_url='https://api-inference.modelscope.cn/v1'
    )

    # 初始化用户偏好实例（会话级记忆）
    user_pref = UserPreference()
    ## 你好，请帮我查询今天上海的天气，推荐预算500以内的历史文化景点，不要人多的地方。如果推荐的景点门票售罄，请推荐备选。
    
    # 欢迎语
    print("=" * 60)
    print("🎯 智能旅行助手 - 命令行交互模式")
    print("💡 输入需求即可查询天气/推荐景点，输入 'exit'/'退出' 可终止程序")
    print("=" * 60 + "\n")

    # 初始化会话历史
    prompt_history = [user_pref.get_preferences_str()]

    while True:
        # 1. 命令行获取用户输入
        user_input = input("👉 请输入你的旅行需求：").strip()
        
        # 退出机制
        if user_input.lower() in ["exit", "退出", "q", "quit"]:
            print("\n👋 感谢使用智能旅行助手，再见！")
            break
        
        if not user_input:
            print("⚠️ 输入不能为空，请重新输入！\n")
            continue

        # 2. 更新会话历史（添加用户最新输入）
        prompt_history.insert(0, f"用户请求: {user_input}")
        print(f"\n📝 你输入的需求：{user_input}")
        print("-" * 60)

        # 3. 智能体核心处理循环
        task_completed = False
        # 单次请求的最大循环次数（避免无限思考）
        for i in range(8):
            print(f"\n--- 思考步骤 {i + 1} ---")

            # 构建完整Prompt（包含历史+偏好）
            full_prompt = "\n".join(prompt_history)

            # 调用LLM生成思考和行动
            llm_output = llm.generate(full_prompt, system_prompt=AGENT_SYSTEM_PROMPT)
            
            # 截断多余的Thought-Action对
            match = re.search(r'(Thought:.*?Action:.*?)(?=\n\s*(?:Thought:|Action:|Observation:)|\Z)', llm_output, re.DOTALL)
            if match:
                llm_output = match.group(1).strip()
            
            print(f"\n🤖 智能体思考：\n{llm_output}")
            prompt_history.append(llm_output)

            # 解析Action
            action_match = re.search(r"Action: (.*)", llm_output, re.DOTALL)
            if not action_match:
                print("❌ 解析错误：未找到Action")
                break
            
            action_str = action_match.group(1).strip()

            # 任务完成：输出最终答案
            if action_str.startswith("finish"):
                final_answer = re.search(r'finish\(answer="(.*)"\)', action_str).group(1)
                print(f"\n✅ 智能旅行助手回复：\n{final_answer}\n")
                print("=" * 60 + "\n")
                prompt_history.append(f"最终回答: {final_answer}")
                task_completed = True
                break

            # 解析工具调用
            tool_name_match = re.search(r"(\w+)\(", action_str)
            args_match = re.search(r"\((.*)\)", action_str)
            
            if not tool_name_match or not args_match:
                print("❌ 工具调用格式错误")
                break
            
            tool_name = tool_name_match.group(1)
            args_str = args_match.group(1)
            kwargs = dict(re.findall(r'(\w+)="([^"]*)"', args_str))

            # 执行工具并获取结果
            if tool_name in available_tools:
                observation = available_tools[tool_name](** kwargs)
                # 特殊处理：提取偏好后更新用户偏好实例
                if tool_name == "extract_preferences":
                    # 解析提取的偏好并更新
                    for item in observation.split("; "):
                        if ":" in item:
                            key, value = item.split(": ")
                            if key in user_pref.explicit_preferences:
                                user_pref.update_explicit(key, value)
                    # 更新历史中的偏好信息
                    prompt_history[-1] = user_pref.get_preferences_str()
                # 特殊处理：检测到门票售罄
                elif tool_name == "check_ticket_availability" and "售罄" in observation:
                    prompt_history.append(f"Observation: {observation}（触发备选推荐）")
                # 特殊处理：用户拒绝推荐（模拟，实际可通过对话捕获）
                elif tool_name == "get_attraction" and "拒绝" in user_input:
                    user_pref.update_implicit(
                        reject_type=kwargs.get("rejected_type"),
                        reject_reason=kwargs.get("reject_reason")
                    )
                    prompt_history.append(user_pref.get_preferences_str())
            else:
                observation = f"❌ 错误:未定义工具 {tool_name}"

            # 记录工具执行结果
            observation_str = f"Observation: {observation}"
            print(f"\n📊 工具执行结果：\n{observation_str}")
            prompt_history.append(observation_str)

            # 反思机制：连续拒绝≥3次时触发策略调整
            if user_pref.reject_count >= 3:
                print("\n🔍 检测到连续3次拒绝，调整推荐策略...")
                prompt_history.append("Thought: 用户连续拒绝3次推荐，需分析拒绝原因并调整策略")
                prompt_history.append(f"Action: get_attraction(city=\"{kwargs.get('city','')}\", weather=\"{kwargs.get('weather','')}\", preferences=\"避开{user_pref.implicit_preferences['rejected_attraction_types'][0]}，{user_pref.explicit_preferences['budget_range']}\")")
                user_pref.reset_reject_count()  # 重置计数器

        if not task_completed:
            print("\n⚠️ 未能完成你的请求，请简化需求后重新输入！\n")
            print("=" * 60 + "\n")

if __name__ == "__main__":
    # 启动命令行交互
    run_agent_interaction()