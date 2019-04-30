#!/usr/bin/python

#
# Quick and dirty MLT (Kdenlive / Shotcut, etc) to FCPXML (Final Cut Pro, Davinci Resolve) converter.
#
# (C) Gabriel Gambetta 2019. 
# 
# http://gabrielgambetta.com (tech), http://gabrielgambetta.biz (filmmaking), http://twitter.com/gabrielgambetta
#
# Licensed under GPL v3.
# 

import re
import os
import os.path
import sys

from bs4 import BeautifulSoup

# Whether to turn an embedded .kdenlive file into a compound clip, or leave it alone.
# Doesn't work in all cases. A possible workaround is to convert the embedded .kdenlive independently,
# import it as a timeline in Resolve, and replacing the missing clip with the imported timeline.
EMBEDDED_MLT_TO_COMPOUND_CLIP = False

# Unclear whether these are necessary, since every clip has an absolute offset anyway.
ADD_GAP_NODES = True

# =============================================================================
#  Data model.
# =============================================================================
class ClipFile:
  def __init__(self, resource_path):
    self.resource_path = resource_path

class Clip:
  def __init__(self, clip_id, name, resource, duration):
    self.clip_id = clip_id
    self.name = name
    self.resource = resource
    self.duration = duration

class Entry:
  def __init__(self, clip, in_time, out_time):
    self.clip = clip
    self.in_time = in_time
    self.out_time = out_time

class Track:
  def __init__(self, is_audio):
    self.is_audio = is_audio
    self.entries = []

  def addEntry(self, entry):
    self.entries.append(entry)

global_embed_counter = 0

class Project:
  def __init__(self):
    self.clips = {}
    self.tracks = []
    self.frame_rate = None
    
    global global_embed_counter
    if global_embed_counter == 0:
      self.id_prefix = "ROOT_" if EMBEDDED_MLT_TO_COMPOUND_CLIP else ""
    else:
      self.id_prefix = "EMB_%02d_" % global_embed_counter

    global_embed_counter += 1

  def addClip(self, clip_id, clip):
    self.clips[clip_id] = clip

  def getClip(self, clip_id):
    return self.clips[clip_id]

  def addTrack(self, track):
    self.tracks.append(track)


# =============================================================================
#  Kdenlive reader.
# =============================================================================
def selectFirst(node, selector):
  values = node.select(selector)
  if values:
    return values[0]
  return None

TIME_PATTERN = re.compile(r"(\d\d):(\d\d):(\d\d).(\d\d\d)")
def parseTime(time_str):
  match = TIME_PATTERN.match(time_str)
  hours = int(match.group(1))
  minutes = int(match.group(2))
  seconds = int(match.group(3))
  millis = int(match.group(4))
  return hours*3600 + minutes*60 + seconds + millis/1000.0

class KdenliveReader:
  def __init__(self):
    pass

  def read(self, filename):
    input_file = file(filename, "rb")
    self.soup = BeautifulSoup(input_file, "lxml-xml")
    self.project = Project()

    self._parseSettings()
    self._parseProducers()
    self._parseTracks()
    
    return self.project


  def _parseSettings(self):
    profile = selectFirst(self.soup, "mlt > profile")
    self.project.frame_rate_num = int(profile["frame_rate_num"])
    self.project.frame_rate_den = int(profile["frame_rate_den"])
    self.project.frame_rate = float(self.project.frame_rate_num) / float(self.project.frame_rate_den) 

    self.project.width = int(profile["width"])
    self.project.height = int(profile["height"])
    print "Project format is %d x %d @ %.2f" % (self.project.width, self.project.height, self.project.frame_rate)


  def _parseProducers(self):
    self.resource_path_to_canonical_clip = {}
    self.clip_id_to_canonical_clip_id = {}

    resource_root = selectFirst(self.soup, "mlt")["root"]

    producers = self.soup.select("producer")
    for producer in producers:
      clip_id = producer["id"]
      if clip_id == "black_track":
        continue
      clip_id = self.project.id_prefix + clip_id 

      resource_name = selectFirst(producer, "property[name=resource]").text
      original = selectFirst(producer, "property[name=kdenlive:originalurl]")
      if original:
        resource_name = original.text

      duration = parseTime(producer["out"])

      if re.match(r"[0-9.]+:", resource_name):
        # TODO: preserve slow motion information somewhere.
        colon_idx = resource_name.find(":")
        resource_name = resource_name[colon_idx+1:]

      resource_path = os.path.join(resource_root, resource_name)
      if resource_path in self.resource_path_to_canonical_clip:
        canonical_clip = self.resource_path_to_canonical_clip[resource_path]
        self.clip_id_to_canonical_clip_id[clip_id] = canonical_clip
      else:
        clip_name = os.path.split(resource_path)[1]
        clip_name_attr = selectFirst(producer, "property[name=kdenlive:clipname]")
        if clip_name_attr:
          clip_name = clip_name_attr.text
          if not clip_name:
            clip_name = clip_id

        if EMBEDDED_MLT_TO_COMPOUND_CLIP and resource_path.endswith(".kdenlive"):
          reader = KdenliveReader()
          print "Reading embedded project:", resource_path
          resource = reader.read(resource_path)
        else:
          resource = ClipFile(resource_path)

        clip = Clip(clip_id, clip_name, resource, duration)
  
        self.clip_id_to_canonical_clip_id[clip_id] = clip_id
        self.resource_path_to_canonical_clip[resource_path] = clip_id
        self.project.addClip(clip_id, clip)
        print clip_id, "->", resource_path

    print "Parsed", len(self.project.clips), "clips."


  def _parseTracks(self):
    audio_playlist_ids = set()
    tractors = self.soup.select("tractor")
    for tractor in tractors:
      is_audio_track = selectFirst(tractor, "property[name=kdenlive:audio_track]")
      if is_audio_track:
        print tractor["id"], "is audio"
        tracks = tractor.select("track")
        for track in tracks:
          audio_playlist_ids.add(track["producer"])

    print "Audio playlists:", audio_playlist_ids

    playlists = self.soup.select("playlist")
    
    for playlist in playlists:
      playlist_id = playlist["id"]
      if playlist_id == "main_bin":
        continue

      is_audio = playlist_id in audio_playlist_ids
      track = Track(is_audio)
      #self.project.addTrack(track)

      print "Playlist:", playlist_id, ("[audio]" if is_audio else "[video]")
      for entry in playlist.contents:
        if entry.name == "blank":
          length = parseTime(entry["length"])
          print "\tBlank:", length
          entry = Entry(None, 0, length)
          track.addEntry(entry)
        elif entry.name == "entry":
          producer = self.project.id_prefix + entry["producer"]
          clip_id = self.clip_id_to_canonical_clip_id[producer]
          clip = self.project.getClip(clip_id)
          in_time = parseTime(entry["in"])
          out_time = parseTime(entry["out"])
          print "\t%s [%.3f - %.3f]" % (producer, in_time, out_time)
          entry = Entry(clip, in_time, out_time)
          track.addEntry(entry)

      if track.entries:
        self.project.addTrack(track)



# =============================================================================
#  FCP XML writer.
# =============================================================================
class FcpXmlWriter:
  def __init__(self, project):
    self.xml = BeautifulSoup(features="xml")
    self.added_embedded_resources = set()
    self.project = project

  def write(self, filename):
    root = self._addTag(self.xml, "fcpxml", version="1.5")

    resources_tag = self._addTag(root, "resources")
    self._addFormats(resources_tag)
    self._addResources(resources_tag)
    
    library = self._addTag(root, "library")
    self._addLibrary(library)
    
    file(filename, "wb").write(self.xml.prettify())


  def _addFormats(self, resources_tag):
    format_tag = self._addTag(resources_tag, "format")
    format_tag["width"] = self.project.width
    format_tag["height"] = self.project.height
    format_tag["id"] = "r0"
    format_tag["frameDuration"] = "1000/%ds" % int(self.project.frame_rate * 1000)


  def _addResources(self, resources_tag):
    for clip_id, clip in self.project.clips.iteritems():
      resource = clip.resource
      if isinstance(resource, ClipFile):
        asset = self._addTag(resources_tag, "asset")
        asset["name"] = clip.name
        asset["id"] = clip_id
        asset["src"] = "file://" + resource.resource_path
        asset["hasVideo"] = 1
        asset["duration"] = self._formatTime(clip.duration)
      elif isinstance(resource, Project):
        self._addEmbeddedTimeline(clip_id, resources_tag)


  def _addEmbeddedTimeline(self, clip_id, resources_tag):
    clip = project.clips[clip_id]
    embedded_project = clip.resource
    writer = FcpXmlWriter(embedded_project)
    if embedded_project not in self.added_embedded_resources:
      self.added_embedded_resources.add(embedded_project)
      writer._addResources(resources_tag)

    media = self._addTag(resources_tag, "media")
    media["name"] = clip.name
    media["id"] = clip_id
    writer._addSequence(media, True)


  def _addLibrary(self, library_tag):
    event = self._addTag(library_tag, "event")
    event["name"] = "Timeline 1"
    project_tag = self._addTag(event, "project")
    project_tag["name"] = "Timeline 1"
    self._addSequence(project_tag, False)


  def _addSequence(self, project_tag, wrap_in_clip):
    sequence = self._addTag(project_tag, "sequence")
    sequence["format"] = "r0"
    spine = self._addTag(sequence, "spine")

    if wrap_in_clip:
      wrapper = self._addTag(spine, "clip")
      wrapper["duration"] = self._formatTime(self._getProjectLength())
    else:
      wrapper = spine

    index = 0
    for track in self.project.tracks:
      self._addTrack(track, wrapper, index)
      index += 1


  # Computes the project length, given by the latest out-time it contains.
  def _getProjectLength(self):
    latest_out = 0
    for track in self.project.tracks:
      for entry in track.entries:
        latest_out = max(latest_out, entry.out_time)
    return latest_out


  def _addTrack(self, track, spine, index):
    offset = 0
    for entry in track.entries:
      clip = entry.clip
      duration = entry.out_time - entry.in_time

      if clip is None:
        if ADD_GAP_NODES:
          clip_node = self._addTag(spine, "gap")
        else:
          offset += duration
          continue
      else:
        resource = clip.resource
        if isinstance(resource, ClipFile):
          clip_tag_name = "audio" if track.is_audio else "video"
          clip_node = self._addTag(spine, clip_tag_name)
          one_frame_in_sec = 0.001 + 1.0 / self.project.frame_rate  # TODO: should use frame rate of clip
          duration += + one_frame_in_sec
        elif isinstance(resource, Project):
          clip_node = self._addTag(spine, "ref-clip")
          clip_node["srcEnable"] = "audio" if track.is_audio else "video"
          self._addFakeTimemap(clip_node)

        clip_node["name"] = clip.name
        clip_node["ref"] = clip.clip_id

      clip_node["start"] = self._formatTime(entry.in_time)
      clip_node["duration"] = self._formatTime(duration)
      clip_node["offset"] = self._formatTime(offset)
      if index > 0:
        clip_node["lane"] = index

      offset += duration


  # Adds a <timeMap> node that forces Resolve to create a compound clip, although the speed we set is 100%.
  def _addFakeTimemap(self, clip_node):
    timemap = self._addTag(clip_node, "timeMap")

    timept = self._addTag(timemap, "timept")
    timept["time"] = "0/1s"
    timept["value"] = "0/1s"

    timept = self._addTag(timemap, "timept")
    timept["time"] = "1/1s"
    timept["value"] = "10/10s"


  def _formatTime(self, seconds):
    # TODO: use frame rate? Use GCD?
    if seconds == int(seconds):
      return str(int(seconds)) + "/1s"
    return "%d/1000s" % int(seconds * 1000)


  def _addTag(self, node, tagName, **attributes):
    tag = self.xml.new_tag(tagName, **attributes)
    node.append(tag)
    return tag




# =============================================================================
#  Main
# =============================================================================
if __name__ == "__main__":
  if len(sys.argv) < 2:
    print "Usage: mlt2fcp.py input.kdenlive [output.fcpxml]"
    print
    print "If the output filename is not given, replaces the extension of the input file with .fcpxml."
    sys.exit(1)

  input_filename = sys.argv[1]
  if len(sys.argv) > 2:
    output_filename = sys.argv[2]
  else:
    output_filename = os.path.splitext(input_filename)[0] + ".fcpxml"

  reader = KdenliveReader()
  project = reader.read(input_filename)

  writer = FcpXmlWriter(project)
  writer.write(output_filename)
