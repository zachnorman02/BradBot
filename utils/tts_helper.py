import os
import typing
import logging

logger = logging.getLogger('bradbot.tts')

# Try importing optional providers at module load time so imports live at top-level.
# If they are unavailable, set the module vars to None and raise later when used.
try:
    import boto3
    _boto3 = boto3
except Exception:
    _boto3 = None

try:
    from gtts import gTTS
    _gTTS = gTTS
except Exception:
    _gTTS = None


def synthesize_tts_to_file(text: str, out_path: str, voice: str = None, engine: str = None, language: str = None) -> None:
    """Synthesize `text` to `out_path` (mp3 recommended).

    Provider selection via env var `BRADBOT_TTS_PROVIDER`:
      - 'gtts' (default): uses gTTS library
      - 'polly': uses AWS Polly (requires boto3 and AWS creds/config)

    Optionally set `voice`, `engine`, and `language` to customize Polly synthesis.
    """
    # Validate inputs
    if not text:
        raise ValueError("The 'text' parameter cannot be None or empty.")
    if not out_path:
        raise ValueError("The 'out_path' parameter cannot be None or empty.")

    provider = os.getenv('BRADBOT_TTS_PROVIDER', 'gtts').strip().lower()
    engine_to_use = engine or os.getenv('BRADBOT_TTS_ENGINE', 'standard').strip().lower()
    text_to_use = text or 'Alarm'

    # Validate engine
    valid_engines = ['standard', 'neural', 'long-form', 'generative']
    if engine_to_use not in valid_engines:
        raise ValueError(f"Invalid engine '{engine_to_use}'. Valid options are: {', '.join(valid_engines)}")

    # Print as well as log so systemd/journal captures this even if logging is not configured
    print(f'[bradbot.tts] TTS provider selected: {provider}, Engine: {engine_to_use}')
    logger.info('TTS provider selected: %s, Engine: %s', provider, engine_to_use)

    if provider == 'polly':
        if not _boto3:
            raise RuntimeError('boto3 is required for Polly provider; install boto3')

        voice_to_use = voice or os.getenv('BRADBOT_TTS_VOICE', 'Matthew')
        language_to_use = language or os.getenv('BRADBOT_TTS_LANGUAGE', 'en-US')
        region = os.getenv('AWS_REGION') or os.getenv('AWS_DEFAULT_REGION')
        if not region:
            raise RuntimeError("AWS region not configured for Polly. Set AWS_REGION or AWS_DEFAULT_REGION in the environment "
                               "(for example, in your systemd unit: Environment=AWS_REGION=us-east-1), or configure a default region in ~/.aws/config or via instance metadata."
            )

        client = _boto3.client('polly', region_name=region)
        try:
            resp = client.synthesize_speech(
                Text=text_to_use,
                OutputFormat='mp3',
                VoiceId=voice_to_use,
                Engine=engine_to_use,
                LanguageCode=language_to_use
            )
            stream = resp.get('AudioStream')
            if stream is None:
                raise RuntimeError('No AudioStream in Polly response')
            with open(out_path, 'wb') as f:
                f.write(stream.read())
        except Exception as e:
            # Print to stdout so systemd/journal shows the error even without logging configured
            print(f'[bradbot.tts] Polly TTS synthesis failed: {e}')
            logger.exception('Polly TTS synthesis failed')
            raise
        finally:
            try:
                if 'stream' in locals() and hasattr(stream, 'close'):
                    stream.close()
            except Exception:
                pass
    else:
        # fallback to gTTS
        if not _gTTS:
            raise RuntimeError('gTTS is required as a fallback provider; install gTTS')

        try:
            tts = _gTTS(text=text_to_use, lang=language or 'en')
            tts.save(out_path)
        except Exception as e:
            print(f'[bradbot.tts] gTTS synthesis failed: {e}')
            logger.exception('gTTS synthesis failed')
            raise
