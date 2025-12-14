import os
import typing

def synthesize_tts_to_file(text: str, out_path: str) -> None:
    """Synthesize `text` to `out_path` (mp3 recommended).

    Provider selection via env var `BRADBOT_TTS_PROVIDER`:
      - 'gtts' (default): uses gTTS library
      - 'polly': uses AWS Polly (requires boto3 and AWS creds/config)

    Optionally set `BRADBOT_TTS_VOICE` to select a Polly voice (default 'Matthew').
    """
    provider = os.getenv('BRADBOT_TTS_PROVIDER', 'gtts').strip().lower()
    text_to_use = text or 'Alarm'

    if provider == 'polly':
        try:
            import boto3
        except Exception as e:
            raise RuntimeError('boto3 is required for Polly provider; install boto3') from e

        voice = os.getenv('BRADBOT_TTS_VOICE', 'Matthew')
        client = boto3.client('polly')
        try:
            # Polly can return an audio stream; write it to file
            resp = client.synthesize_speech(Text=text_to_use, OutputFormat='mp3', VoiceId=voice)
            stream = resp.get('AudioStream')
            if stream is None:
                raise RuntimeError('No AudioStream in Polly response')
            with open(out_path, 'wb') as f:
                f.write(stream.read())
        finally:
            try:
                if hasattr(stream, 'close'):
                    stream.close()
            except Exception:
                pass
    else:
        # fallback to gTTS
        try:
            from gtts import gTTS
        except Exception as e:
            raise RuntimeError('gTTS is required as a fallback provider; install gTTS') from e

        t = gTTS(text=text_to_use, lang='en')
        t.save(out_path)
