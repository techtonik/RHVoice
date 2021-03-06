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

import os.path
import Queue
from collections import OrderedDict,defaultdict
import threading
from ctypes import c_char_p,c_short,sizeof,string_at,byref,cast

from RHVoice import RHVoice_tts_engine
from RHVoice import RHVoice_init_params, RHVoice_callback_types, RHVoice_callbacks
from RHVoice import RHVoice_synth_params
from RHVoice import RHVoice_message_type, RHVoice_punctuation_mode, RHVoice_capitals_mode
from RHVoice import load_tts_library, get_library_location

import config
import nvwave
from logHandler import log
from synthDriverHandler import SynthDriver,VoiceInfo
import speech
import languageHandler
import addonHandler

config_path=os.path.join(config.getUserDefaultConfigPath(),"RHVoice-config")

def escape_text(text):
    parts=list()
    for c in text:
        if c.isspace():
            part=u"&#{};".format(ord(c))
        elif c=="<":
            part=u"&lt;"
        elif c==">":
            part=u"&gt;"
        elif c=="&":
            part=u"&amp;"
        elif c=="'":
            part=u"&apos;"
        elif c=='"':
            part=u"&quot;"
        else:
            part=c
        parts.append(part)
    return u"".join(parts)

class speech_callback(object):
    def __init__(self,lib,player,cancel_flag):
        self.__lib=lib
        self.__player=player
        self.__cancel_flag=cancel_flag

    def __call__(self,samples,count,user_data):
        try:
            if self.__cancel_flag.is_set():
                return 0
            try:
                self.__player.feed(string_at(samples,count*sizeof(c_short)))
            except:
                log.debugWarning("Error feeding audio to nvWave",exc_info=True)
            return 1
        except:
            log.error("RHVoice speech callback",exc_info=True)
            return 0

class mark_callback(object):
    def __init__(self,lib):
        self.__lib=lib
        self.__lock=threading.Lock()
        self.__index=None

    @property
    def index(self):
        with self.__lock:
            return self.__index

    @index.setter
    def index(self,value):
        with self.__lock:
            self.__index=value

    def __call__(self,name,user_data):
        try:
            self.index=int(name)
            return 1
        except:
            log.error("RHVoice mark callback",exc_info=True)
            return 0

class speak_text(object):
    def __init__(self,lib,tts_engine,text,cancel_flag):
        self.__lib=lib
        self.__tts_engine=tts_engine
        self.__text=text.encode("utf-8")
        self.__cancel_flag=cancel_flag
        self.__synth_params=RHVoice_synth_params(voice_profile=None,
                                                 absolute_rate=0,
                                                 relative_rate=1,
                                                 absolute_pitch=0,
                                                 relative_pitch=1,
                                                 absolute_volume=0,
                                                 relative_volume=1,
                                                 punctuation_mode=RHVoice_punctuation_mode.default,
                                                 punctuation_list=None,
                                                 capitals_mode=RHVoice_capitals_mode.default)

    def set_rate(self,rate):
        self.__synth_params.absolute_rate=rate/50.0-1

    def set_pitch(self,pitch):
        self.__synth_params.absolute_pitch=pitch/50.0-1

    def set_volume(self,volume):
        self.__synth_params.absolute_volume=volume/50.0-1

    def set_voice_profile(self,name):
        self.__synth_params.voice_profile=name

    def __call__(self):
        if self.__cancel_flag.is_set():
            return
        msg=self.__lib.RHVoice_new_message(self.__tts_engine,
                                           self.__text,
                                           len(self.__text),
                                           RHVoice_message_type.ssml,
                                           byref(self.__synth_params),
                                           None)
        if msg:
            self.__lib.RHVoice_speak(msg)
            self.__lib.RHVoice_delete_message(msg)

class TTSThread(threading.Thread):
    def __init__(self,tts_queue):
        self.__queue=tts_queue
        threading.Thread.__init__(self)
        self.daemon=True

    def run(self):
        while True:
            try:
                task=self.__queue.get()
                if task is None:
                    break
                else:
                    task()
            except:
                log.error("RHVoice: error while executing a tts task",exc_info=True)

class SynthDriver(SynthDriver):
    name="RHVoice"
    description="RHVoice"

    supportedSettings=(SynthDriver.VoiceSetting(),
                       SynthDriver.RateSetting(),
                       SynthDriver.PitchSetting(),
                       SynthDriver.VolumeSetting())

    @classmethod
    def check(cls):
        return os.path.isfile(get_library_location())

    def __init__(self):
        self.__lib=load_tts_library()
        self.__cancel_flag=threading.Event()
        self.__player=nvwave.WavePlayer(channels=1,samplesPerSec=16000,bitsPerSample=16,outputDevice=config.conf["speech"]["outputDevice"])
        self.__speech_callback=speech_callback(self.__lib,self.__player,self.__cancel_flag)
        self.__c_speech_callback=RHVoice_callback_types.play_speech(self.__speech_callback)
        self.__mark_callback=mark_callback(self.__lib)
        self.__c_mark_callback=RHVoice_callback_types.process_mark(self.__mark_callback)
        resource_paths=[os.path.join(addon.path,"data").encode("UTF-8") for addon in addonHandler.getRunningAddons() if (addon.name.startswith("RHVoice-language") or addon.name.startswith("RHVoice-voice"))]
        c_resource_paths=(c_char_p*(len(resource_paths)+1))(*(resource_paths+[None]))
        init_params=RHVoice_init_params(None,
                                        config_path.encode("utf-8"),
                                        c_resource_paths,
                                        RHVoice_callbacks(self.__c_speech_callback,
                                                          self.__c_mark_callback,
                                                          cast(None,RHVoice_callback_types.word_starts),
                                                          cast(None,RHVoice_callback_types.word_ends),
                                                          cast(None,RHVoice_callback_types.sentence_starts),
                                                          cast(None,RHVoice_callback_types.sentence_ends),
                                                          cast(None,RHVoice_callback_types.play_audio)),
                                        0)
        self.__tts_engine=self.__lib.RHVoice_new_tts_engine(byref(init_params))
        if not self.__tts_engine:
            raise RuntimeError("RHVoice: initialization error")
        nvda_language=languageHandler.getLanguage().split("_")[0]
        number_of_voices=self.__lib.RHVoice_get_number_of_voices(self.__tts_engine)
        native_voices=self.__lib.RHVoice_get_voices(self.__tts_engine)
        self.__voice_languages=dict()
        self.__languages=set()
        for i in xrange(number_of_voices):
            native_voice=native_voices[i]
            self.__voice_languages[native_voice.name]=native_voice.language
            self.__languages.add(native_voice.language)
        self.__profile=None
        self.__profiles=list()
        number_of_profiles=self.__lib.RHVoice_get_number_of_voice_profiles(self.__tts_engine)
        native_profile_names=self.__lib.RHVoice_get_voice_profiles(self.__tts_engine)
        for i in xrange(number_of_profiles):
            name=native_profile_names[i]
            self.__profiles.append(name)
            if (self.__profile is None) and (nvda_language==self.__voice_languages[name.split("+")[0]]):
                self.__profile=name
        if self.__profile is None:
            self.__profile=self.__profiles[0]
        self.__rate=50
        self.__pitch=50
        self.__volume=50
        self.__tts_queue=Queue.Queue()
        self.__tts_thread=TTSThread(self.__tts_queue)
        self.__tts_thread.start()
        log.info("Using RHVoice version {}".format(self.__lib.RHVoice_get_version()))

    def terminate(self):
        self.cancel()
        self.__tts_queue.put(None)
        self.__tts_thread.join()
        self.__player.close()
        self.__lib.RHVoice_delete_tts_engine(self.__tts_engine)
        self.__tts_engine=None

    def speak(self,speech_sequence):
        spell_mode=False
        language_changed=False
        text_list=[u"<speak>"]
        for item in speech_sequence:
            if isinstance(item,basestring):
                s=escape_text(unicode(item))
                text_list.append((u'<say-as interpret-as="characters">{}</say-as>'.format(s)) if spell_mode else s)
            elif isinstance(item,speech.IndexCommand):
                text_list.append('<mark name="%d"/>' % item.index)
            elif isinstance(item,speech.CharacterModeCommand):
                if item.state:
                    spell_mode=True
                else:
                    spell_mode=False
            elif isinstance(item,speech.LangChangeCommand):
                if language_changed:
                    text_list.append(u"</voice>")
                    language_changed=False
                if not item.lang:
                    continue
                new_language=item.lang.split("_")[0]
                if new_language not in self.__languages:
                    continue
                elif new_language==self.__voice_languages[self.__profile.split("+")[0]]:
                    continue
                text_list.append(u'<voice xml:lang="{}">'.format(new_language))
                language_changed=True
            elif isinstance(item,speech.SpeechCommand):
                log.debugWarning("Unsupported speech command: %s"%item)
            else:
                log.error("Unknown speech: %s"%item)
        if language_changed:
            text_list.append(u"</voice>")
        text_list.append(u"</speak>")
        text=u"".join(text_list)
        task=speak_text(self.__lib,self.__tts_engine,text,self.__cancel_flag)
        task.set_voice_profile(self.__profile)
        task.set_rate(self.__rate)
        task.set_pitch(self.__pitch)
        task.set_volume(self.__volume)
        self.__tts_queue.put(task)

    def pause(self,switch):
        self.__player.pause(switch)

    def cancel(self):
        try:
            while True:
                self.__tts_queue.get_nowait()
        except Queue.Empty:
            self.__cancel_flag.set()
            self.__tts_queue.put(self.__cancel_flag.clear)
            self.__player.stop()

    def _get_lastIndex(self):
        return self.__mark_callback.index

    def _get_availableVoices(self):
        return OrderedDict((profile,VoiceInfo(profile,profile,self.__voice_languages[profile.split("+")[0]])) for profile in self.__profiles)

    def _get_language(self):
        return self.__voice_languages[self.__profile.split("+")[0]]

    def _get_rate(self):
        return self.__rate

    def _set_rate(self,rate):
        self.__rate=max(0,min(100,rate))

    def _get_pitch(self):
        return self.__pitch

    def _set_pitch(self,pitch):
        self.__pitch=max(0,min(100,pitch))

    def _get_volume(self):
        return self.__volume

    def _set_volume(self,volume):
        self.__volume=max(0,min(100,volume))

    def _get_voice(self):
        return self.__profile

    def _set_voice(self,voice):
        try:
            self.__profile=self.availableVoices[voice].ID
        except:
            pass
