import re
import random

# 规则库：严格按「具体规则→宽泛规则→兜底规则」排序
rules = {
    # 原有核心规则
    r'Do you remember (.*)\?': [
        "Of course I remember, {0}.",
        "Yes, I have kept that in mind about you."
    ],

    r'I need (.*)': [
        "Why do you need {0}?",
        "Would it really help you to get {0}?",
        "Are you sure you need {0}?"
    ],
    r'Why don\'t you (.*)\?': [
        "Do you really think I don't {0}?",
        "Perhaps eventually I will {0}.",
        "Do you really want me to {0}?"
    ],
    r'Why can\'t I (.*)\?': [
        "Do you think you should be able to {0}?",
        "If you could {0}, what would you do?",
        "I don't know -- why can't you {0}?"
    ],
    r'I am (.*)': [
        "Did you come to me because you are {0}?",
        "How long have you been {0}?",
        "How do you feel about being {0}?"
    ],
    # 新增的具体规则（优先匹配）
    r'I hate learning(.*)': [  # 比宽泛的.*study.*更具体，优先
        "Why would you feel so?",
        "Tell me more about your hatred on {0}.",
        "What do you think would make you feel better?"
    ],
    r'I like (.*)': [
        "Why do you like {0}?",  # 修正原模板的小问题：it→{0}更准确
        "Is it helpful for you to unwind with {0}?",
        "Could you share more about {0}?"
    ],

    # 宽泛规则（匹配包含某个关键词的句子）
    r'.* mother .*': [
        "Tell me more about your mother.",
        "What was your relationship with your mother like?",
        "How do you feel about your mother?"
    ],
    r'.* father .*': [
        "Tell me more about your father.",
        "How did your father make you feel?",
        "What has your father taught you?"
    ],
    r'.* study .*': [
        "How do you feel about study?",
        "Do you have any plan on learning?",
        "Is there anything easy or happy when you study?"
    ],
    r'.* work .*': [
        "Is it your ideal job? If not, what kind of work would you prefer?",
        "Would it make you exhausted?",
        "Do you gain any achievement from it?"
    ],
    # 兜底规则（最后匹配）
    r'.*': [
        "Please tell me more.",
        "Let's change focus a bit... Tell me about your family.",
        "Can you elaborate on that?"
    ]
}

# 代词转换规则
pronoun_swap = {
    "i": "you", "you": "i", "me": "you", "my": "your",
    "am": "are", "are": "am", "was": "were", "i'd": "you would",
    "i've": "you have", "i'll": "you will", "yours": "mine",
    "mine": "yours"
}

user_memory = {
    "name": "",
    "age":"",
    "job":"",
    "hobby":""
}
# 新增：标记是否是首次记住用户的关键信息（姓名/年龄），初始为False
# 在 “首次记住姓名 / 年龄” 时，把is_first_memory设为True（后续只触发一次）
is_first_memory = False

def update_user_memory(user_input):
    """
    从用户输入中提取姓名、年龄、职业，并更新到上下文记忆字典中
    输入：user_input - 用户的对话输入
    输出：无，直接修改全局的user_memory字典
    """
    # 先声明要使用全局的user_memory字典（函数内修改全局变量需要声明global）
    global user_memory
    # 新增：声明使用全局的is_first_memory变量
    global is_first_memory

    # 先记录更新前的记忆状态（判断是否是首次记住）
    has_name_before = bool(user_memory["name"])  # 之前是否有姓名（True/False）
    has_age_before = bool(user_memory["age"])    # 之前是否有年龄
    
    # 1. 匹配并提取姓名（英文句式，和你的ELIZA保持一致）
    # 匹配 "My name is XXX" 或 "I am XXX"（XXX是姓名）
    name_match = re.search(r'My name is (.*)', user_input, re.IGNORECASE)
    if name_match:
        # 获取匹配到的内容（group(1)或group(2)，哪个有值取哪个）
        name1 = name_match.group(1) if name_match.group(1) else ""
        # name2 = name_match.group(2) if name_match.group(2) else ""
        user_name = name1.strip() # or name2.strip()  # 去除首尾空格，避免无效信息
        # 如果提取到了有效姓名，更新记忆
        if user_name:
            user_memory["name"] = user_name
            # print(f"（悄悄记住：用户姓名是 {user_name}）")  # 调试用
    
    # 2. 匹配并提取年龄（英文句式）
    # 匹配 "I am XXX years old" 或 "I am XXX years of age"
    age_match = re.search(r'I am (.*) years old|I am (.*) years of age', user_input, re.IGNORECASE)
    if age_match:
        age1 = age_match.group(1) if age_match.group(1) else ""
        age2 = age_match.group(2) if age_match.group(2) else ""
        user_age = age1.strip() or age2.strip()
        if user_age:
            user_memory["age"] = user_age
            # print(f"（悄悄记住：用户年龄是 {user_age}）")  # 调试用
    
    # 3. 匹配并提取职业（英文句式）
    # 匹配 "My job is XXX" 或 "I work as a XXX"
    job_match = re.search(r'My job is (.*)|I work as a (.*)|I am a (.*)|I am an (.*)', user_input, re.IGNORECASE)
    if job_match:
        job1 = job_match.group(1) if job_match.group(1) else ""
        job2 = job_match.group(2) if job_match.group(2) else ""
        job3 = job_match.group(3) if job_match.group(3) else ""
        job4 = job_match.group(4) if job_match.group(4) else ""
        user_job = job1.strip() or job2.strip() or job3.strip() or job4.strip()
        if user_job:
            user_memory["job"] = user_job
            # print(f"（悄悄记住：用户职业是 {user_job}）")  # 调试用

    hobby_match = re.search(r'I like to (.*)|My hobby is (.*)', user_input, re.IGNORECASE)
    if hobby_match:
        hobby1 = hobby_match.group(1) if hobby_match.group(1) else ""
        hobby2 = hobby_match.group(2) if hobby_match.group(2) else ""
        user_hobby = hobby1.strip() or hobby2.strip()
        if user_hobby:
            user_memory["hobby"] = user_hobby
    
    # 新增核心逻辑：判断是否是首次记住姓名/年龄（之前没有，现在有了）
    has_name_now = bool(user_memory["name"])
    has_age_now = bool(user_memory["age"])

    # 只有“之前没有，现在有了”，才标记为首次记忆
    if (not has_name_before and has_name_now) or (not has_age_before and has_age_now):
        is_first_memory = True
    else:
        is_first_memory = False  # 不是首次，重置标记


def swap_pronouns(phrase):
    """转换第一/第二人称代词"""
    words = phrase.lower().split()
    swapped_words = [pronoun_swap.get(word, word) for word in words]
    return " ".join(swapped_words)

def respond(user_input):
    """生成响应：按规则顺序匹配，匹配到立即返回"""

    # 新增：获取记忆中的用户姓名
    user_name = user_memory["name"]
    user_age = user_memory["age"]
    user_job = user_memory["job"]
    user_hobby = user_memory["hobby"]
    memory_info = []

    # 遍历规则（按定义顺序）
    for pattern, responses in rules.items():
        # 忽略大小写匹配
        match = re.search(pattern, user_input.strip(), re.IGNORECASE)
        if match:
            # 获取捕获的内容（如果有）
            captured = match.group(1) if match.groups() else ""
            # 代词转换
            swapped = swap_pronouns(captured)
            # 随机选一个响应并格式化
            response = random.choice(responses).format(swapped)

            # 优化：针对"你知道关于我的什么信息？"专门整合记忆
            if pattern == r'What do you know about me\?':
                if user_name:
                    memory_info.append(f"your name is {user_name}")
                if user_age:
                    memory_info.append(f"you are {user_age} years old")
                if user_job:
                    memory_info.append(f"your job is a {user_job}")
                if user_hobby:
                    memory_info.append(f"your hobby is {user_hobby}")
                if memory_info:
                    response = f"I know that {', '.join(memory_info)}."
            
            # 普通规则的姓名引用（可选保留）
            elif user_name and not memory_info:
                response = f"{response}, {user_name}"

            return response
    
    # 理论上不会走到这里（因为有.*兜底）
    # 兜底规则也添加姓名引用
    default_response = random.choice(rules[r'.*'])
    if user_name:
        default_response = f"{default_response}, {user_name}"
    return default_response

# 主循环
if __name__ == '__main__':
    print("Therapist: Hello! How can I help you today?")
    therapist_resp = ''
    while True:
        user_input = input("You: ")
        # 新增：提取用户输入中的关键信息，更新记忆
        update_user_memory(user_input)

        # 退出条件
        if user_input.strip().lower() in ["quit", "exit", "bye"]:
            print("Therapist: Goodbye. It was nice talking to you.")
            break

               # 新增：如果是首次记住用户信息，添加友好开场白
        if is_first_memory:
            # 准备友好话术列表（随机选一个，更自然）
            welcome_phrases = [
                f"Nice to meet you, {user_memory['name']}! What would you like to talk about?",
                f"It's great to know you, {user_memory['name']}! Is there anything you want to share with me?",
                f"Pleased to meet you, {user_memory['name']}! Feel free to talk about anything you like."
            ]
            # 随机选一个友好话术 + 原有响应（用换行分隔，更流畅）
            welcome_phrase = random.choice(welcome_phrases)
            therapist_resp = f"{welcome_phrase}\n{therapist_resp}"
        else:
            # 生成并打印响应
            therapist_resp = respond(user_input)

        print(f"Therapist: {therapist_resp}")
