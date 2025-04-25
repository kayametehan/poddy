import speech_recognition as sr
import google.generativeai as genai
from elevenlabs.client import ElevenLabs
from elevenlabs import Voice, VoiceSettings
import playsound                         # Ses çalmak için
import tempfile                          # Geçici dosya oluşturmak için
import os                                # Dosya işlemleri için
from dotenv import load_dotenv
import sys
import time                              # Küçük bekleme eklemek için
import traceback                         # Hata ayıklama için

# .env dosyasındaki değişkenleri yükle
load_dotenv()

# API Anahtarlarını al
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "Rachel") # Varsayılan ses

# --- API İstemcilerini Başlatma ---

# Google Gemini
if not GOOGLE_API_KEY:
    print("HATA: Google API anahtarı .env dosyasında bulunamadı.")
    sys.exit(1)
try:
    genai.configure(api_key=GOOGLE_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-1.5-flash') # Veya başka bir model
    print("Google Gemini başarıyla başlatıldı.")
except Exception as e:
    print(f"HATA: Google Gemini başlatılamadı: {e}")
    sys.exit(1)

# ElevenLabs
if not ELEVENLABS_API_KEY:
    print("HATA: ElevenLabs API anahtarı .env dosyasında bulunamadı.")
    sys.exit(1)
try:
    elevenlabs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
    print(f"ElevenLabs başarıyla başlatıldı. Kullanılacak Ses ID: {ELEVENLABS_VOICE_ID}")
except Exception as e:
    print(f"HATA: ElevenLabs başlatılamadı: {e}")
    sys.exit(1)

# --- Ses Tanıma ve Sentezleme Fonksiyonları ---

# Ses Tanıma (Speech-to-Text)
def listen_for_command(recognizer, microphone):
    """Mikrofonu dinler ve Türkçe komutu metne çevirir."""
    with microphone as source:
        print("\nDinliyorum...")
        try:
            # recognizer.adjust_for_ambient_noise(source, duration=0.5) # Her seferinde yapmak yerine başta bir kere yapmak daha iyi
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)
        except sr.WaitTimeoutError:
            print("Zaman aşımı: Komut algılanmadı.")
            return None
        except Exception as e:
            print(f"Dinleme sırasında beklenmedik hata: {e}")
            return None

    try:
        print("Anlamaya çalışıyorum...")
        command = recognizer.recognize_google(audio, language='tr-TR')
        print(f"Siz: {command}")
        return command.lower()
    except sr.UnknownValueError:
        print("Ne dediğinizi anlayamadım.")
        return None
    except sr.RequestError as e:
        print(f"Ses tanıma servisine ulaşılamadı; {e}")
        return None
    except Exception as e:
        print(f"Ses tanıma sırasında beklenmedik hata: {e}")
        return None

# Gemini Yanıtı Alma (Text Generation)
def get_gemini_response(prompt, model):
    """Verilen metin girdisine Gemini'den yanıt alır."""
    try:
        print("Gemini düşünüyor...")
        response = model.generate_content(prompt)

        if response.parts:
            text_response = response.text
            print(f"Gemini: {text_response}")
            return text_response
        else:
            error_message = "Üzgünüm, buna uygun bir yanıt oluşturamadım."
            if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                 print(f"Gemini Geri Bildirimi: {response.prompt_feedback}")
                 # block_reason = getattr(response.prompt_feedback, 'block_reason', None)
                 # if block_reason: error_message += f" (Sebep: {block_reason})"
            print(f"Gemini: {error_message}")
            return error_message

    except Exception as e:
        print(f"Gemini ile iletişim hatası: {e}")
        return "Üzgünüm, yapay zeka ile konuşurken bir sorun oluştu."

# ElevenLabs ile Konuşma (Text-to-Speech) - GENERATOR HATASI DÜZELTİLMİŞ VERSİYON
def speak_with_elevenlabs(text, client, voice_id):
    """Verilen metni ElevenLabs kullanarak sentezler ve playsound ile çalar."""
    if not text:
        print("Konuşacak metin boş.")
        return

    temp_audio_path = None
    try:
        print("ElevenLabs sentezliyor...")
        # Generate fonksiyonu bir generator döndürebilir. stream=True kullanmak daha iyi.
        audio_stream_generator = client.generate(
            text=text,
            voice=Voice(
                voice_id=voice_id,
                # İsteğe bağlı: settings=VoiceSettings(stability=0.7, similarity_boost=0.6)
            ),
            model='eleven_multilingual_v2', # Türkçe için iyi bir model
            stream=True # Akış olarak al (generator döndürür)
        )

        # Generator'dan gelen tüm byte parçalarını birleştir
        print("Ses verisi alınıyor...")
        accumulated_bytes = b"".join(chunk for chunk in audio_stream_generator)
        print(f"Toplam {len(accumulated_bytes)} byte ses verisi alındı.")

        if not accumulated_bytes:
            print("HATA: ElevenLabs'tan boş ses verisi alındı. Metin veya API ile ilgili sorun olabilir.")
            return

        # Toplanan byte verisini geçici bir MP3 dosyasına yaz
        print("Geçici dosyaya yazılıyor...")
        # delete=False -> dosya kapandıktan sonra silinmez, biz sileceğiz
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
            fp.write(accumulated_bytes)
            temp_audio_path = fp.name # Geçici dosyanın tam yolunu al

        print(f"Ses oynatılıyor ({os.path.basename(temp_audio_path)})...")
        playsound.playsound(temp_audio_path)
        # playsound'un dosyayı hemen bırakmama ihtimaline karşı küçük bekleme
        time.sleep(0.2)
        print("Oynatma tamamlandı.")

    except Exception as e:
        print(f"Ses sentezleme veya oynatma hatası ({type(e).__name__}): {e}")
        # Hatanın kaynağını daha iyi anlamak için tam traceback'i yazdırabiliriz:
        # traceback.print_exc()
    finally:
        # Geçici dosyayı sil (hata olsa bile silmeye çalış)
        if temp_audio_path and os.path.exists(temp_audio_path):
            try:
                os.remove(temp_audio_path)
                # print(f"Geçici dosya silindi: {temp_audio_path}") # Hata ayıklama için
            except PermissionError:
                 print(f"Uyarı: Geçici dosya ({temp_audio_path}) hemen silinemedi. Muhtemelen hala kilitli.")
            except Exception as e:
                 print(f"Uyarı: Geçici dosya ({temp_audio_path}) silinirken hata: {e}")


# --- Ana Çalışma Döngüsü ---
if __name__ == "__main__":
    # Gerekli nesneleri oluştur
    r = sr.Recognizer()
    mic = sr.Microphone()

    # Başlangıçta ortam gürültüsüne göre ayarlama yap (sadece bir kere)
    with mic as source:
        print("Ortam gürültüsüne göre ayarlanıyor... Lütfen 1-2 saniye sessiz olun.")
        try:
             r.adjust_for_ambient_noise(source, duration=1.5) # Süreyi ayarlayabilirsiniz
             print("Gürültü ayarı tamamlandı. Asistan hazır.")
        except Exception as e:
             print(f"Mikrofon gürültü ayarı sırasında hata: {e}. Varsayılanlarla devam ediliyor.")

    # Başlangıç mesajı
    speak_with_elevenlabs("Merhaba, ben sizin sesli asistanınızım. Nasıl yardımcı olabilirim?", elevenlabs_client, ELEVENLABS_VOICE_ID)

    # Ana dinleme ve yanıt döngüsü
    while True:
        command = listen_for_command(r, mic)

        if command:
            # Çıkış komutları (daha fazla kelime eklenebilir)
            if any(word in command for word in ["güle güle", "hoşça kal", "kapat", "çıkış", "bitir"]):
                speak_with_elevenlabs("Görüşmek üzere, kendinize iyi bakın!", elevenlabs_client, ELEVENLABS_VOICE_ID)
                print("\nAsistan kapatılıyor...")
                break

            # Komut anlaşıldıysa, Gemini'ye gönder
            gemini_response = get_gemini_response(command, gemini_model)

            # Gemini'den geçerli bir yanıt geldiyse seslendir
            if gemini_response:
                speak_with_elevenlabs(gemini_response, elevenlabs_client, ELEVENLABS_VOICE_ID)
            else:
                # Gemini boş yanıt döndürdüyse veya hata oluştuysa kullanıcıyı bilgilendir
                speak_with_elevenlabs("Üzgünüm, bir yanıt alamadım.", elevenlabs_client, ELEVENLABS_VOICE_ID)

        else:
            # Komut anlaşılamadıysa veya zaman aşımı olduysa tekrar dinle
            # İsteğe bağlı olarak burada "Anlayamadım, tekrar eder misiniz?" gibi bir mesaj eklenebilir.
            # speak_with_elevenlabs("Üzgünüm, anlayamadım.", elevenlabs_client, ELEVENLABS_VOICE_ID)
            pass # Döngü devam eder ve tekrar dinlemeye başlar