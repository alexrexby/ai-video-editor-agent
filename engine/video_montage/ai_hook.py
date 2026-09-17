import requests
from typing import Optional, List, Dict
from .config import POLZA_API_KEY, AI_BASE_URL, LLM_MODEL

class AIHookGenerator:
    """Generates viral hooks and context emojis for short-form videos."""

    def __init__(self, api_key: str = POLZA_API_KEY, base_url: str = AI_BASE_URL, model: str = LLM_MODEL):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    def generate_hook(self, transcript_text: str) -> Optional[str]:
        """Generates a punchy 2-4 word hook banner for the first 3 seconds."""
        if not transcript_text.strip():
            return None

        prompt = (
            "Ты продюсер вирусных коротких видео (Reels, Shorts, TikTok).\n"
            "Познакомься с речью спикера в начале ролика:\n\n"
            f'"{transcript_text[:400]}"\n\n'
            "Придумай ОДИН короткий, цепляющий, провокационный заголовок-хук для плашки на первые 3 секунды ролика.\n"
            "Требования:\n"
            "- От 2 до 4 слов максимум;\n"
            "- ТОЛЬКО заглавными буквами (CAPS);\n"
            "- Бьет в боль, интригу или парадокс;\n"
            "- БЕЗ кавычек, точек и смайлов в ответе, только текст хука.\n\n"
            "Примеры:\n"
            "ГЛАВНАЯ ОШИБКА НОВИЧКА\n"
            "ТЕБЕ ВРАЛИ ВСЕ ЭТИ ГОДЫ\n"
            "ПОЧЕМУ ТВОЙ БИЗНЕС СТОИТ\n"
            "СЕКРЕТ БОЛЬШИХ ЧЕКОВ"
        )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 50
        }

        try:
            resp = requests.post(f"{self.base_url}/chat/completions", headers=headers, json=body, timeout=15)
            if resp.status_code == 200:
                hook = resp.json()["choices"][0]["message"]["content"].strip().strip('"\'«»')
                # Guarantee uppercase
                return hook.upper()
        except Exception as e:
            print(f"[AIHookGenerator] Error generating hook: {e}")

        return None

    def add_emojis_to_words(self, words: List[Dict[str, any]]) -> List[Dict[str, any]]:
        """Adds context emoji to punchy words (e.g. деньги -> 💰, огонь -> 🔥)."""
        EMOJI_DICTIONARY = {
            "деньги": "💰", "денег": "💰", "доход": "💸", "рублей": "💵", "долларов": "💵", "продажи": "📈",
            "ошибка": "❌", "ошибок": "❌", "нельзя": "⛔️", "стоп": "🛑", "внимание": "⚠️", "секрет": "🤫",
            "шок": "😱", "огонь": "🔥", "ракета": "🚀", "быстро": "⚡️", "цель": "🎯", "топ": "🔝",
            "команда": "👥", "люди": "👥", "клиент": "🤝", "клиенты": "🤝", "партнер": "🤝",
            "вопрос": "❓", "почему": "🤔", "идея": "💡", "круто": "😎", "успех": "🏆", "победа": "🥇"
        }

        for item in words:
            clean_word = item["word"].lower().strip(".,!?:;\"'«»")
            if clean_word in EMOJI_DICTIONARY:
                item["emoji"] = EMOJI_DICTIONARY[clean_word]

        return words
