# SivrisinekCenk

Türkçe konuşan, kalıcı hafızalı, görüntü algılayabilen Discord botu. Tüm LLM trafiği **lokal** çalışır (LM Studio, `llama-server`, vLLM, Ollama vb. OpenAI-compat sunucu) — Anthropic/OpenAI API'sine bağımlı değildir.

## Özellikler

- **Türkçe persona** — `prompts/persona.txt` dosyasını editleyerek karakteri/üslubu değiştir, kod dokunmadan.
- **Lokal LLM** — `OPENAI_BASE_URL` ile herhangi bir OpenAI-uyumlu sunucuya bağlanır (default `http://localhost:8000/v1`).
- **Multi-modal (vision)** — kullanıcı bir mesajla beraber `image/*` attach ederse bot resmi görüp yorumlar (vision-capable model gerek; resim bot tarafından base64 olarak inline edilir, LLM sunucusu Discord CDN'e ulaşmak zorunda kalmaz).
- **Konuşma hafızası (kısa vadeli)** — kanal başına 2 saatlik sliding session, max 100 mesaj.
- **Kalıcı hafıza (uzun vadeli, restart sonrası kalır)** — ChromaDB tabanlı yerel vector store (MemPalace), 3 kapsam:
  - `user` — sana özel, hangi kanalda olursan ol hatırlanır
  - `channel` — bu kanalın ortak bağlamı
  - `guild` — tüm sunucu çapında, her kanalda hatırlanır
- **Tool calling** — model "şunu hatırla", "kaydet", "unutma" gibi açık komutları ya da kalıcı bir bilgiyi tespit ettiğinde `save_memory` tool'unu **kendisi** çağırarak hafızaya yazar (gemma-4-it gibi function-calling destekli modellerle).
- **Otomatik fact extraction** — fallback olarak her N user mesajında bir LLM konuşmadan kalıcı bilgileri damıtır (default 8).
- **Slash komutları** — `/clear`, `/remember`, `/forget`, `/memory_list`, `/memory`.
- **TR DPI bypass** — Discord SNI engellemesini SpoofDPI proxy ile aşar (`start.sh` orkestrasyonu).
- **Preflight checks** — bot başlamadan LLM sunucusunu, Discord erişimini ve memory backend'ini test eder; sessizce hang yerine açıklayıcı hata.

## Kurulum

### 1) Bağımlılıklar
```bash
pip install -r requirements.txt
```
`mempalace` ilk kurulumda chromadb + onnxruntime + sentence-transformers çekiyor (~300 MB). İlk botu çalıştırdığında embedding modeli (`all-MiniLM-L6-v2`, ~80 MB) Chroma'nın S3 mirror'undan indirilir — Hugging Face bağımlılığı yok, TR'den DPI sorunu olmaz.

### 2) Yerel LLM sunucusu
OpenAI-uyumlu herhangi bir sunucu yeterli. Örnekler:
- **LM Studio** → "Start Server" düğmesi (default port 1234, `OPENAI_BASE_URL=http://localhost:1234/v1`)
- **llama.cpp** → `llama-server -m model.gguf --port 3131` (vision için `--mmproj mmproj.gguf` da gerekir)
- **Ollama** → `ollama serve` + OpenAI-compat shim
- **vLLM** → `vllm serve <model>`

Model **vision-capable** olmalı (görsel destek için), ve **tool-calling** desteklemeli (kalıcı hafıza yazımı için). Test edilmiş kombinasyon: `gemma-4-26B-A4B-it` GGUF + mmproj.

### 3) `.env`
```bash
cp .env.example .env
```
Sonra düzenle:
```env
DISCORD_TOKEN=...                              # zorunlu
OPENAI_BASE_URL=http://localhost:3131/v1       # LLM sunucu adresi
OPENAI_MODEL=gemma-4-26B-A4B-it-Q4_K_M.gguf    # served model id
GUILD_ID=                                      # geliştirmede sunucu ID (slash anında sync)
DISCORD_PROXY=http://127.0.0.1:8080            # TR'deysen SpoofDPI; değilsen boş bırak
```

### 4) (TR'deysen) SpoofDPI
```bash
# https://github.com/xvzc/SpoofDPI'dan binary indir, örn:
SPOOFDPI_BIN=/Users/sen/Desktop/spoofdpi
```
`start.sh` :8080'i otomatik kontrol eder, boşsa `-window-size 1` flag'iyle başlatır (aiohttp'nin TLS deseninde DPI'yı atlatmak için aggressive Client Hello fragmentation gerek).

### 5) Çalıştır
```bash
./start.sh
```
`start.sh` SpoofDPI'ı (gerekiyorsa) başlatır, sonra bot'u foreground'da çalıştırır. Çıktı:
```
[start] SpoofDPI :8080 already running, reusing
[preflight] LLM (...) and Discord via http://127.0.0.1:8080 OK
[preflight] memory palace at ~/.sivrisinekcenk/mempalace OK
[discord.gateway] Shard ID None has connected to Gateway
SivrisinekCenk yayında! ... hazır.
```

> **Not:** `start.sh` LLM sunucusunu **başlatmaz** — onu sen ayrıca başlatırsın. Preflight LLM'in ayakta olduğunu kontrol eder, değilse hint'le çıkış yapar.

## Kullanım

### Bot ile konuşma
Bot şu üç durumdan birinde cevap verir:
1. `@SivrisinekCenk` ile mention edildiğinde
2. Mesajda ismi geçtiğinde (case-insensitive)
3. Bot'un kendi mesajına reply atıldığında

> ⚠️ Bot cevap vermese de **kanaldaki tüm mesajlar** session history'sine eklenir. Sonraki cevaplarda bağlam olarak görür.

### Slash komutları

| Komut | Açıklama |
|---|---|
| `/clear` | Bu kanaldaki **kısa hafızayı** sıfırlar (2 saatlik session). Kalıcı hafıza dokunulmaz. |
| `/remember scope:<user\|channel\|guild> text:<...>` | Kalıcı hafızaya **manuel** not ekle. |
| `/forget scope:<...> confirm:"evet sil"` | Belirtilen scope'un kalıcı hafızasını **tamamen** siler. Geri alınamaz. |
| `/memory_list scope:<...>` | O scope'un mevcut notlarını listeler (max 30, ephemeral). |
| `/memory` | Tek seferde sana özel + bu kanal + (varsa) bu sunucu hafızasının **özetini** code block'ta dump eder. |

### Doğal dilde hafıza yazma
Tool calling sayesinde:
> Sen: `@bot Kaan en çok muzu sever, bunu hatırla`
> Bot: model `save_memory(scope="user", fact="Kaan en çok muz sever")` tool'unu çağırır, ChromaDB'ye yazılır, sonra "Tamamdır, kaydettim" cevabını verir. `/memory` çekersen orada gözükür.

DM'de `scope=guild` kullanılamaz (sunucu kavramı yok), bot net hata mesajı döner.

## Mimari (kısa)

```
bot.py            — Discord client + slash commands + on_message akışı
config.py         — .env yükleme; DISCORD_TOKEN, OPENAI_*, MEMPALACE_*, vb.
llm_client.py     — AsyncOpenAI wrapper (tools desteği var)
session_store.py  — Kanal başına in-memory sliding session
memory_manager.py — MemPalace adapter; user/channel/guild wing'leri, retrieval, auto-extract
tools.py          — LLM'e gösterilen tool tanımları (save_memory)
prompts/
  persona.txt        — Sistem promptu (persona)
  extract_facts.txt  — Auto-extract LLM promptu
start.sh          — SpoofDPI + bot orkestrasyonu
```

`on_message` akışı:
1. Mesajı session history'ye ekle
2. Trigger kontrolü (mention/name/reply)
3. Multi-modal içerik hazırla (resim varsa base64)
4. `query_relevant` ile **3 paralel** search (user + channel + guild) → notes inject
5. `_run_with_tools` ile LLM çağrı (tools=[save_memory], max 4 iter)
6. Cevabı reply olarak gönder + session'a yaz
7. Auto-extract task'ı arka planda fire-et (her N mesajda bir tetiklenir)

## Konfigürasyon

| Env | Default | Açıklama |
|---|---|---|
| `DISCORD_TOKEN` | — (zorunlu) | Discord bot token |
| `OPENAI_BASE_URL` | `http://localhost:8000/v1` | LLM sunucu adresi |
| `OPENAI_API_KEY` | `not-needed` | Lokal sunucular ignore eder ama boş olamaz |
| `OPENAI_MODEL` | `TrevorJS/gemma-4-E2B-it-uncensored-GGUF/...` | Model identifier |
| `SESSION_TTL_SECONDS` | `7200` | Sliding session expiry (2 saat) |
| `HISTORY_MAX_MESSAGES` | `100` | Session başına max mesaj |
| `GUILD_ID` | boş | Set edilirse slash sync guild-scoped (anında); değilse global (~1 saat) |
| `DISCORD_PROXY` | boş | TR DPI için SpoofDPI proxy (örn. `http://127.0.0.1:8080`) |
| `MEMPALACE_PATH` | `~/.sivrisinekcenk/mempalace` | Persistent memory storage path |
| `MEMORY_AUTO_EXTRACT` | `true` | Auto-extract aktif/pasif |
| `MEMORY_EXTRACT_EVERY_N_MESSAGES` | `8` | Auto-extract eşiği |
| `MEMORY_RETRIEVAL_K` | `3` | Her scope için retrieve edilecek not sayısı |
| `MEMORY_MIN_FACT_LEN` | `6` | Bu uzunluğun altındaki fact'ler reddedilir |

## Sorun giderme

- **Bot "logging in" mesajından sonra sessizce takılıyor** — Discord SNI engellemesi (TR). `DISCORD_PROXY=http://127.0.0.1:8080` set et ve SpoofDPI çalıştır.
- **`Error 500: image input is not supported`** — LLM sunucun vision-capable değil. `llama-server`'ı `--mmproj` flag'iyle başlat.
- **Slash komutlar Discord'da görünmüyor** — `GUILD_ID` boşsa global sync 1 saate kadar sürer. Geliştirmede `GUILD_ID` set et.
- **`/memory` boş ama bot "kaydettim" demişti** — Bu sadece konuşma; gerçek kayıt için tool calling gerekiyor (model çağırmadıysa) veya manuel `/remember`.
- **Memory backend init failed** — `~/.sivrisinekcenk/mempalace` yazılabilir mi? `pip install mempalace` çalıştı mı? İlk run'da embedding model indirme başarısız mı?

## Lisans

Şu an açık değil. Repo private kullanım için.
