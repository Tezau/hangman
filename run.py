import sounddevice as sd
import soundfile as sf
import speech_recognition as sr
from deep_translator import GoogleTranslator

import sounddevice as sd
import soundfile as sf

seconds = 10
samplerate = 48000
channels = 2
filename = "temp.wav"

#print(sd.query_devices())

# выбери устройство VB-Cable
device_id = 3  # CABLE Output (VB-Audio Virtual Cable), Windows WASAPI (2 in, 0 out)

print("Запись системного звука...")
recording = sd.rec(int(seconds * samplerate),
                   samplerate=samplerate,
                   channels=channels,
                   device=device_id,
                   blocking=True)

sf.write(filename, recording, samplerate)
print(f"Файл сохранён: {filename}")

def simple_recognize():
    # Распознавание
    r = sr.Recognizer()
    with sr.AudioFile('temp.wav') as source:
        audio = r.record(source)

    try:
        text = r.recognize_google(audio, language='en-EN')
        print(f"Распознано: {text}")

        # Перевод
        translated = GoogleTranslator(source='en', target='ru').translate(text)
        print(f"Перевод: {translated}")

    except sr.UnknownValueError:
        print("Речь не распознана")
    except sr.RequestError as e:
        print(f"Ошибка сервиса: {e}")


if __name__ == "__main__":
    simple_recognize()