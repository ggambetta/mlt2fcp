# MLT2FCP

Quick and dirty MLT (Kdenlive / Shotcut, etc) to FCPXML (Final Cut Pro, Davinci Resolve) converter.

Copyright (C) Gabriel Gambetta 2019. 

[Tech website](http://gabrielgambetta.com), [Filmmaking website](http://gabrielgambetta.biz), [Twitter](http://twitter.com/gabrielgambetta)


## Introduction

This is a quick and dirty converter from MLT video project files (in particular, the Kdenlive 19+ dialect, but might work with others)
to Final Cut Pro XML (in particular, one that Davinci Resolve can import).

It's buggy and alpha; I stopped fixing bugs and adding features when my particular itch was scratched. It did successfully convert a 45 minute
timeline with O(1000) entries pretty accurately (with a total accumulated error of less than a second)


## Known issues

* There's some off-by-one error somewhere, I believe caused by rounding times in milliseconds to frames. As a result, audio and video clips might
  be shifted by a frame, or be a frame too long.

* Nested clips (a .kdenlive clip in the timeline) are supported, but don't work very well; sometimes Resolve imports the result correctly, sometimes
  it doesn't.
  
  * Processing nested clips is disabled by default. As a result, the container timeline will contain references to a missing .kdenlive file. These can be
  converted independently, imported as timelines into Resolve, and the missing clip replaced with the imported timeline.
