# -*- coding: utf-8 -*-
#
# Picard, the next-generation MusicBrainz tagger
# Copyright (C) 2006-2007 Lukáš Lalinský
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.

import mutagen.apev2
import mutagen.mp3
import mutagen.trueaudio
from mutagen import id3
from picard.file import File
from picard.formats.mutagenext import compatid3
from picard.util import encode_filename

class ID3File(File):
    """Generic ID3-based file."""
    _File = None
    _IsMP3 = False

    IDS = {
        'TPE1': 'artist',
        'TPE2': 'albumartist',
        'TPE3': 'conductor',
        'TPE4': 'remixer',
        'TCOM': 'composer',
        'TCON': 'genre',
        'TALB': 'album',
        'TIT1': 'grouping',
        'TIT2': 'title',
        'TIT3': 'subtitle',
        'TEXT': 'lyricist',
        'TCMP': 'compilation',
        'TDRC': 'date',
        'XDOR': 'date',
        'COMM': 'comment',
        'TMOO': 'mood',
        'TBPM': 'bpm',
        'WOAR': 'website',
        'TSRC': 'isrc',
        'TENC': 'encodedby',
        'TCOP': 'copyright',
        'TSOA': 'album_sortorder',
        'TSOP': 'artist_sortorder',
        'TSOT': 'title_sortorder',
    }

    TXXXS = {
        'MusicBrainz Artist Id': 'musicbrainz_artistid',
        'MusicBrainz Album Id': 'musicbrainz_albumid',
        'MusicBrainz Album Artist Id': 'musicbrainz_albumartistid',
    }

    def read(self):
        file = self._File(encode_filename(self.filename), ID3=compatid3.CompatID3)
        tags = file.tags or {}
        metadata = self.metadata

        for frame in tags.values():
            frameid = frame.FrameID
            if frameid in self.IDS:
                name = self.IDS[frameid]
                if frameid.startswith('T'):
                    for text in frame.text:
                        metadata.add(name, unicode(text))
                elif frameid == 'COMM':
                    for text in frame.text:
                        metadata.add('%s:%s' % (name, frame.desc), unicode(text))
                else:
                    metadata.add(name, unicode(frame))
            elif frameid == 'TXXX' and frame.desc in self.TXXXS:
                name = self.TXXXS[frame.desc]
                for text in frame.text:
                    metadata.add(name, unicode(text))
            elif frameid == 'UFID' and frame.owner == 'http://musicbrainz.org':
                metadata['musicbrainz_trackid'] = unicode(frame.data)
            elif frameid == 'TRCK':
                value = frame.text[0].split('/')
                if len(value) > 1:
                    metadata['tracknumber'], metadata['totaltracks'] = value[:2]
                else:
                    metadata['tracknumber'] = value[0]
            elif frameid == 'TPOS':
                value = frame.text[0].split('/')
                if len(value) > 1:
                    metadata['discnumber'], metadata['totaldiscs'] = value[:2]
                else:
                    metadata['discnumber'] = value[0]
            elif frameid == 'APIC':
                metadata.add('~artwork', (frame.mime, frame.data))

        self._info(file)
        self.orig_metadata.copy(self.metadata)

    def save(self):
        """Save metadata to the file."""
        try:
            tags = compatid3.CompatID3(encode_filename(self.filename))
        except mutagen.id3.ID3NoHeaderError:
            tags = compatid3.CompatID3()
        metadata = self.metadata

        if self.config.setting['clear_existing_tags']:
            tags.clear()
        if self.config.setting['remove_images_from_tags']:
            tags.delall('APIC')

        if self.config.setting['write_id3v1']: v1 = 2
        else: v1 = 0
        encoding = {'utf-8': 3, 'utf-16': 1}.get(self.config.setting['id3v2_encoding'], 0)

        id3.TCMP = compatid3.TCMP
        for frameid, name in self.IDS.items():
            if frameid.startswith('X'):
                continue
            if name in metadata:
                if frameid.startswith('W'):
                    tags.add(getattr(id3, frameid)(url=metadata[name]))
                else:
                    tags.add(getattr(id3, frameid)(encoding=encoding, text=metadata.getall(name)))
        for desc, name in self.TXXXS.items():
            if name in metadata:
                tags.add(id3.TXXX(encoding=encoding, desc=desc, text=metadata[name]))
        if 'musicbrainz_trackid' in metadata:
            tags.add(id3.UFID(owner='http://musicbrainz.org', data=str(metadata['musicbrainz_trackid'])))
        if 'tracknumber' in metadata:
            if 'totaltracks' in metadata:
                text = '%s/%s' % (metadata['tracknumber'], metadata['totaltracks'])
            else:
                text = metadata['tracknumber']
            tags.add(id3.TRCK(encoding=0, text=text))
        if 'discnumber' in metadata:
            if 'totaldiscs' in metadata:
                text = '%s/%s' % (metadata['discnumber'], metadata['totaldiscs'])
            else:
                text = metadata['discnumber']
            tags.add(id3.TPOS(encoding=0, text=text))
        if self.config.setting['save_images_to_tags']:
            images = self.metadata.getall('~artwork')
            for mime, data in images:
                tags.add(id3.APIC(encoding=0, mime=mime, type=3, desc='', data=data))

        if self.config.setting['write_id3v23']:
            tags.update_to_v23()
            tags.save(encode_filename(self.filename), v2=3, v1=v1)
        else:
            tags.update_to_v24()
            tags.save(encode_filename(self.filename), v2=4, v1=v1)

        if self._IsMP3 and self.config.setting['strip_ape_tags']:
            try: mutagen.apev2.delete(encode_filename(self.filename))
            except: pass

class MP3File(ID3File):
    """MP3 file."""
    _File = mutagen.mp3.MP3
    _IsMP3 = True
    def _info(self, file):
        super(MP3File, self)._info(file)
        self.metadata['~format'] = 'MPEG-1 Layer %d' % file.info.layer

class TrueAudioFile(ID3File):
    """TTA file."""
    _File = mutagen.trueaudio.TrueAudio
    def _info(self, file):
        super(TrueAudioFile, self)._info(file)
        self.metadata['~format'] = 'The True Audio'
