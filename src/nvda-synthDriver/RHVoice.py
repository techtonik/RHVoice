# -*- coding: utf-8 -*-
# Copyright (C) 2010, 2011, 2012, 2013  Olga Yakovleva <yakovleva.o.v@gmail.com>

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
import sys
import time
import wave

from ctypes import CDLL, CFUNCTYPE, POINTER, Structure, c_char_p, c_double
from ctypes import c_int, c_uint, c_short, c_void_p, byref, sizeof, string_at


# --- bindings ---

class RHVoice_tts_engine_struct(Structure):
    pass
RHVoice_tts_engine=POINTER(RHVoice_tts_engine_struct)

class RHVoice_message_struct(Structure):
    pass
RHVoice_message=POINTER(RHVoice_message_struct)


class RHVoice_callback_types:
    play_speech=CFUNCTYPE(c_int,POINTER(c_short),c_uint,c_void_p)
    process_mark=CFUNCTYPE(c_int,c_char_p,c_void_p)
    word_starts=CFUNCTYPE(c_int,c_uint,c_uint,c_void_p)
    word_ends=CFUNCTYPE(c_int,c_uint,c_uint,c_void_p)
    sentence_starts=CFUNCTYPE(c_int,c_uint,c_uint,c_void_p)
    sentence_ends=CFUNCTYPE(c_int,c_uint,c_uint,c_void_p)
    play_audio=CFUNCTYPE(c_int,c_char_p,c_void_p)

class RHVoice_callbacks(Structure):
    _fields_=[("play_speech",RHVoice_callback_types.play_speech),
              ("process_mark",RHVoice_callback_types.process_mark),
              ("word_starts",RHVoice_callback_types.word_starts),
              ("word_ends",RHVoice_callback_types.word_ends),
              ("sentence_starts",RHVoice_callback_types.sentence_starts),
              ("sentence_ends",RHVoice_callback_types.sentence_ends),
              ("play_audio",RHVoice_callback_types.play_audio)]

class RHVoice_init_params(Structure):  # from RHVoice.h
    _fields_=[("data_path",c_char_p),
              ("config_path",c_char_p),
              ("resource_paths",POINTER(c_char_p)),
              ("callbacks",RHVoice_callbacks),
              ("options",c_uint)]


class RHVoice_voice_info(Structure):
    _fields_=[("language",c_char_p),
              ("name",c_char_p),
              ("gender",c_int)]

class RHVoice_synth_params(Structure):
    _fields_=[("voice_profile",c_char_p),
              ("absolute_rate",c_double),
              ("absolute_pitch",c_double),
              ("absolute_volume",c_double),
              ("relative_rate",c_double),
              ("relative_pitch",c_double),
              ("relative_volume",c_double),
              ("punctuation_mode",c_int),
              ("punctuation_list",c_char_p),
              ("capitals_mode",c_int)]

class RHVoice_message_type:
    text=0
    ssml=1
    characters=2

class RHVoice_voice_gender:
    unknown=0
    male=1
    female=2

class RHVoice_punctuation_mode:
    default=0
    none=1
    all=2
    some=3

class RHVoice_capitals_mode:
    default=0
    off=1
    word=2
    pitch=3
    sound=4

# --- main code ---

module_dir=os.path.dirname(__file__.decode(sys.getfilesystemencoding()))
RHVoice_lib_path=os.path.join(module_dir,"RHVoice.dll")

def load_tts_library():
    lib=CDLL(RHVoice_lib_path.encode(sys.getfilesystemencoding()))
    lib.RHVoice_get_version.restype=c_char_p
    lib.RHVoice_new_tts_engine.argtypes=(POINTER(RHVoice_init_params),)
    lib.RHVoice_new_tts_engine.restype=RHVoice_tts_engine
    lib.RHVoice_delete_tts_engine.argtypes=(RHVoice_tts_engine,)
    lib.RHVoice_delete_tts_engine.restype=None
    lib.RHVoice_get_number_of_voices.argtypes=(RHVoice_tts_engine,)
    lib.RHVoice_get_number_of_voices.restype=c_uint
    lib.RHVoice_get_voices.argtypes=(RHVoice_tts_engine,)
    lib.RHVoice_get_voices.restype=POINTER(RHVoice_voice_info)
    lib.RHVoice_get_number_of_voice_profiles.argtypes=(RHVoice_tts_engine,)
    lib.RHVoice_get_number_of_voice_profiles.restype=c_uint
    lib.RHVoice_get_voice_profiles.argtypes=(RHVoice_tts_engine,)
    lib.RHVoice_get_voice_profiles.restype=POINTER(c_char_p)
    lib.RHVoice_are_languages_compatible.argtypes=(RHVoice_tts_engine,c_char_p,c_char_p)
    lib.RHVoice_are_languages_compatible.restype=c_int
    lib.RHVoice_new_message.argtypes=(RHVoice_tts_engine,c_char_p,c_uint,c_int,POINTER(RHVoice_synth_params),c_void_p)
    lib.RHVoice_new_message.restype=RHVoice_message
    lib.RHVoice_delete_message.arg_types=(RHVoice_message,)
    lib.RHVoice_delete_message.restype=None
    lib.RHVoice_speak.argtypes=(RHVoice_message,)
    lib.RHVoice_speak.restype=c_int
    return lib


class SpeechCallback(object):
    """
    This is a callable object for using in RHVoice speech_callback. The
    only obligatory part is __call__() method with its parameters.
    """
    sample_size = sizeof(c_short)

    def __init__(self):
        self.counter = 0
        self.datasize = 0
        self.starttime = time.clock()

    def __call__(self, samples, count, user_data):
        """Should return False to stop synthesis"""
        self.counter += 1
        size = count*self.sample_size
        self.datasize += size
        kbps = self.datasize / (time.clock() - self.starttime) / 1024
        self.debug(count, size, kbps)
        return True

    def debug(self, count, size, kbps):
        print("speech callback %s time(s) samples: %s, size: %s, %.2f kBps" % (self.counter, count, size, kbps))

class WaveWriteCallback(SpeechCallback):
    def __init__(self, filename, ):
        super(WaveWriteCallback, self).__init__()
        self.wavefile = wave.open(filename, 'wb')
        self.wavefile.setnchannels(1)
        self.wavefile.setsampwidth(self.sample_size)
        self.wavefile.setframerate(16000)

    def __call__(self, samples, count, user_data):
        """Should return False to stop synthesis"""
        self.wavefile.writeframes(string_at(samples, count*self.sample_size))
        return True

def main():
    usage = "RHVoice.py [-o filename] \"text\""

    # --- process params ---
    import optparse
    parser = optparse.OptionParser(usage=usage)
    parser.add_option("-i", "--input",
                      help="file with text encoded in UTF-8")
    parser.add_option("-o", "--output", default="output.wav",
                      help="output filename (default: output.wav)")
    opts, args = parser.parse_args()
    if not args and not opts.input:
        parser.print_help()
        print("\nError: No input text")
        sys.exit(-1)

    # --- setup synthesizer and main ---

    lib = load_tts_library()
    lib.RHVoice_set_logging(True)
    print("RHVoice %s" % lib.RHVoice_get_version())

    init_params = RHVoice_init_params()
    # need to set callbacks with .play_speech set, or RHVoice_new_tts_engine will fail
    #speech_callback = SpeechCallback()
    speech_callback = WaveWriteCallback(opts.output)
    c_speech_callback = RHVoice_callback_types.play_speech(speech_callback)
    callbacks = RHVoice_callbacks()
    callbacks.play_speech = c_speech_callback
    init_params.callbacks = callbacks

    """
    RHVoice_callbacks(self.__c_speech_callback,
        self.__c_mark_callback,
        cast(None,RHVoice_callback_types.word_starts),
        cast(None,RHVoice_callback_types.word_ends),
        cast(None,RHVoice_callback_types.sentence_starts),
        cast(None,RHVoice_callback_types.sentence_ends),
        cast(None,RHVoice_callback_types.play_audio)),
    """

    engine = lib.RHVoice_new_tts_engine(byref(init_params))
    if not engine:
        raise RuntimeError("RHVoice: engine initialization error")
    voices_total = lib.RHVoice_get_number_of_voices(engine)
    print("Number of voices: %s" % voices_total)
    first_voice = lib.RHVoice_get_voices(engine)
    print("    Voice     Language  Gender")
    for voiceno in range(voices_total):
        vi = first_voice[voiceno]
        print(" %-16s  %2s    %2s " % (vi.name, vi.language, vi.gender))

    profiles_total = lib.RHVoice_get_number_of_voice_profiles(engine)
    profiles = []
    first_profile = lib.RHVoice_get_voice_profiles(engine)
    print("Voice Profiles")
    for profno in range(profiles_total):
        print(" %s" % first_profile[profno])
        profiles.append(first_profile[profno])

    # transform text to RHVoice_message for RHVoice_speak 
    # RHVoice_new_message is a function to do so. Its parameters:
    # (RHVoice_tts_engine, c_char_p, c_uint, c_int, POINTER(RHVoice_synth_params), c_void_p)
    # (tts_engine, const char* text, length, RHVoice_message_type,   synth_params, void* user_data)

    text_en = "this is a test text phrase"
    text_ru = "Значит так, короче, в общем, я считаю дело к ночи"

    text = ""
    if args:
        text += args[0]
    else:
        text += open(opts.input, "rb").read()

    # message also specifies voice parameters, which are obligatory
    synth_params = RHVoice_synth_params()
    synth_params.voice_profile = profiles[0]
    synth_params.relative_pitch = 1.0
    synth_params.relative_rate = 1.0

    message = lib.RHVoice_new_message(engine,
                                      text,
                                      len(text),
                                      RHVoice_message_type.text,
                                      byref(synth_params),
                                      None)

    if not message:
        raise RuntimeError("RHVoice: message building error")
    lib.RHVoice_speak(message)
    lib.RHVoice_delete_message(message)  # free the memory (check when message is stored)

if __name__ == '__main__':
    main()
