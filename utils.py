import re

def normalize_phone(phone: str) -> str:
    return re.sub(r'\D', '', phone)

def role_priority(role: str) -> int:
    priorities = {
        "користувач": 0,
        "дилер": 1,
        "менеджер": 2,
        "адмін": 3,
        "старший адмін": 4
    }
    return priorities.get(role, 0)
