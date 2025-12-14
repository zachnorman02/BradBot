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


def synthesize_tts_to_file(text: str, out_path: str) -> None:
    """Synthesize `text` to `out_path` (mp3 recommended).

    Provider selection via env var `BRADBOT_TTS_PROVIDER`:
      - 'gtts' (default): uses gTTS library
      - 'polly': uses AWS Polly (requires boto3 and AWS creds/config)

    Optionally set `BRADBOT_TTS_VOICE` to select a Polly voice (default 'Matthew').
    """
    provider = os.getenv('BRADBOT_TTS_PROVIDER', 'gtts').strip().lower()
    text_to_use = text or 'Alarm'

    # Print as well as log so systemd/journal captures this even if logging is not configured
    print(f'[bradbot.tts] TTS provider selected: {provider}')
    logger.info('TTS provider selected: %s', provider)

    if provider == 'polly':
        if not _boto3:
            raise RuntimeError('boto3 is required for Polly provider; install boto3')

        voice = os.getenv('BRADBOT_TTS_VOICE', 'Matthew')
        # Determine AWS region: prefer explicit env vars. If missing, raise a helpful error.
        region = os.getenv('AWS_REGION') or os.getenv('AWS_DEFAULT_REGION')
        if region:
            client = _boto3.client('polly', region_name=region)
        else:
            raise RuntimeError(
                "AWS region not configured for Polly. Set AWS_REGION or AWS_DEFAULT_REGION in the environment "
                "(for example, in your systemd unit: Environment=AWS_REGION=us-east-1), or configure a default region in ~/.aws/config or via instance metadata."
            )
        try:
            # Polly can return an audio stream; write it to file
            resp = client.synthesize_speech(Text=text_to_use, OutputFormat='mp3', VoiceId=voice)
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
            t = _gTTS(text=text_to_use, lang='en')
            t.save(out_path)
        except Exception as e:
            print(f'[bradbot.tts] gTTS synthesis failed: {e}')
            logger.exception('gTTS synthesis failed')
            raise
