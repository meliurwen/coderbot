############################################################################
#    CoderBot, a didactical programmable robot.
#    Copyright (C) 2014, 2015 Roberto Previtera <info@coderbot.org>
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License along
#    with this program; if not, write to the Free Software Foundation, Inc.,
#    51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
############################################################################

import os
import time
from sys import byteorder
from array import array
from struct import pack
import logging

import pyaudio
import wave
import logging

try:
  from pocketsphinx.pocketsphinx import Decoder
  from sphinxbase.sphinxbase import *
except:
  logging.info("pocketsphinx not available")

CHUNK_SIZE = 4096
FORMAT = pyaudio.paInt16
RATE = 44100

MODELDIR = "/home/pi/coderbot/psmodels/"
SOUNDDIR = "./sounds/"

class Audio:

  _instance = None

  @classmethod
  def get_instance(cls):
    if cls._instance is None:
      cls._instance = Audio()
    return cls._instance

  def say(self, what, locale='en'):
    if what and "$" in what:
      os.system ('omxplayer sounds/' + what[1:])
    elif what and len(what):
      os.system ('espeak -v' + locale + ' -p 90 -a 200 -s 150 -g 10 "' + what + '" 2>>/dev/null')

  def normalize(self, snd_data):
    "Average the volume out"
    MAXIMUM = 16384
    times = float(MAXIMUM)/max(abs(i) for i in snd_data)

    r = array('h')
    for i in snd_data:
        r.append(int(i*times))
    return r

  def record(self, elapse):
    p = pyaudio.PyAudio()
    stream = p.open(format=FORMAT, channels=1, input_device_index=0, rate=RATE,
        input=True,
        frames_per_buffer=CHUNK_SIZE)

    num_silent = 0
    snd_started = False
    c = 0

    r = array('h')

    while (c * 2.0 * 8192 / RATE) < elapse:
      c += 1
      # little endian, signed short
      snd_data = array('h', stream.read(CHUNK_SIZE))
      if byteorder == 'big':
        snd_data.byteswap()
      r.extend(snd_data)

    sample_width = p.get_sample_size(FORMAT)
    stream.stop_stream()
    stream.close()
    p.terminate()
    
    r = self.normalize(r)

    return sample_width, r

  def record_to_file(self, filename, elapse):
    sample_width, data = self.record(elapse)
    data = pack('<' + ('h'*len(data)), *data)

    wf = wave.open(SOUNDDIR + filename, 'wb')
    wf.setnchannels(1)
    wf.setsampwidth(sample_width)
    wf.setframerate(RATE)
    wf.writeframes(data)
    wf.close()

  def play(self, filename):
    # open the file for reading.
    wf = wave.open(SOUNDDIR + filename, 'rb')

    # create an audio object
    p = pyaudio.PyAudio()

    # open stream based on the wave object which has been input.
    stream = p.open(format =
                p.get_format_from_width(wf.getsampwidth()),
                channels = wf.getnchannels(),
                rate = wf.getframerate(),
                output = True)

    # read data (based on the chunk size)
    data = wf.readframes(CHUNK_SIZE)

    # play stream (looping from beginning of file to the end)
    while data != '':
      # writing to the stream is what *actually* plays the sound.
      stream.write(data)
      data = wf.readframes(CHUNK_SIZE)

    # cleanup stuff.
    stream.close()    
    p.terminate()

  def speech_recog(self, model):

    # Create a decoder with certain model
    config = Decoder.default_config()
    config.set_string('-hmm', '/usr/local/share/pocketsphinx/model/en-us/en-us')
    config.set_int('-ds', 2)
    config.set_int('-topn', 3)
    config.set_int('-maxwpf', 5)
    #config.set_string('-kws', MODELDIR + model + '.txt')
    config.set_string('-lm', MODELDIR + model + '.lm')
    config.set_string('-dict', MODELDIR + model + '.dict')
    decoder = Decoder(config)

    p = pyaudio.PyAudio()
    logging.info("device info: " + str(p.get_device_info_by_index(0)))
    #stream = p.open(format=pyaudio.paInt16, channels=1, input_device_index=0, rate=16000, input=True, frames_per_buffer=1024)
    stream = p.open(format=FORMAT, channels=1, input_device_index=0, rate=RATE,
                    input=True,
                    frames_per_buffer=CHUNK_SIZE*256)
    stream.start_stream()
    decoder.start_utt()
    tstamp = time.time()
    recog_text = ''

    while len(recog_text) < 1:
      try:
        buf = stream.read(CHUNK_SIZE)
        logging.info("actual voice")
        decoder.process_raw(buf, False, False)
        if decoder.hyp().hypstr != '':
          recog_text += decoder.hyp().hypstr
          print "text: " + decoder.hyp().hypstr
          tstamp = time.time()
      except IOError as ex:
        if ex[1] != pyaudio.paInputOverflowed:
          raise
        buf = '\x00' * CHUNK_SIZE #white noise
        logging.info("white noise") 
      except AttributeError:
        pass

    decoder.end_utt()
    stream.close()
    p.terminate()

    logging.info("recog text: " + recog_text)
    return recog_text
