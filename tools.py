"""LLM tool definitions exposed to the model via OpenAI-compat function calling."""

SAVE_MEMORY_TOOL = {
    "type": "function",
    "function": {
        "name": "save_memory",
        "description": (
            "Kullanıcı veya kanal hakkında kalıcı bir bilgiyi hafızaya kaydet. "
            "Kullanıcı 'hatırla', 'kaydet', 'unutma', 'not al' gibi açık komutlar verdiğinde "
            "ya da konuşmadan açık bir kişisel/kanal-spesifik gerçek (isim, tercih, meslek, "
            "kanal bağlamı) öğrendiğinde kullan. Geçici durumları ('bugün canım sıkkın', "
            "'yorgunum') KAYDETME. Aynı fact iki kez kaydedilmez (idempotent)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "enum": ["user", "channel"],
                    "description": (
                        "user = mesajı gönderen kişiye özel fact (her kanalda hatırlanır). "
                        "channel = bu kanalın kolektif bağlamı (kanaldaki herkesi etkiler)."
                    ),
                },
                "fact": {
                    "type": "string",
                    "description": (
                        "Hatırlanacak bilgi. Açık, kendi başına anlamlı bir cümle. "
                        "Örnek: 'Kaan en çok muz sever' (✓), 'evet' (✗)."
                    ),
                },
            },
            "required": ["scope", "fact"],
        },
    },
}

TOOLS = [SAVE_MEMORY_TOOL]
