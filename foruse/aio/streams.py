# -*- coding: utf-8 -*-
import asyncio
from foruse import *
from .fs import LocalFS


_local_fs = LocalFS()


class EndLineException(Exception):
	def __str__(self):
		return "End of line excepted"
		
#!endclass EndLineException


class IOException(Exception):
	def __init__(self, value):
		self.value = value
		
	def __str__(self):
		return self.value
		
#!endclass EndLineException


class EofException(Exception):
	def __str__(self):
		return "End of stream"
		
#!endclass EndLineException



class AbstractStream(log.Log):
	
	SEEK_SET = 0
	SEEK_CUR = 1
	SEEK_END = 2
	
	MODE_READ = 'rb'
	MODE_READ_AND_WRITE = 'r+b'
	MODE_WRITE = 'wb'
	MODE_WRITE_AND_READ = 'w+b'
	MODE_APPEND = 'ab'
	MODE_APPEND_AND_READ = 'a+b'
	
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		
		self._loop = kwargs.get('loop')
		if self._loop == None:
			self._loop = asyncio.get_event_loop()
			
		self._chunk_size = kwargs.get('chunk_size', 8192)
		self._read_loop_waiter = None
		self._start_seek = 0
		self._max_buffer_size = 1024
		self._buffer_start = 0
		
		self._buffer = None
		
	def set_min_size(self, size):
		if size <= self._buffer._max_size:
			self._buffer._min_size = size
		
	def _clear_buffer(self):
		self._buffer_start = 0
		self._buffer = None
		
	def seekable(self):
		return False
	
	def writable(self):
		return False
	
	def readable(self):
		return False
	
	# -----------------------------------------------------------------------------
	#                           Abstract Stream Functions
	# -----------------------------------------------------------------------------
	
	async def _open(self):
		return False
	
	async def _close(self):
		pass
	
	async def _read(self, count=-1):
		pass
	
	async def _write(self, buf):
		pass
	
	async def _seek(self, offset, whence):
		pass
	
	async def _tell(self):
		return 0
	
	async def _size(self):
		return None
	
	async def _eof(self):
		return True
	
	async def _flush(self):
		pass
	
	# -----------------------------------------------------------------------------
	#                               Stream Functions
	# -----------------------------------------------------------------------------
	
	async def open(self):
		return await self._open()
	
	
	async def close(self):
		await self._close()
	
	async def eof(self):
		if self._buffer is None:
			return await self._eof()
		
		return False
		
	
	async def flush(self):
		await self._flush()
	
	async def size(self):
		return await self._size()
	
	async def seek(self, offset, whence = SEEK_SET):
		self._clear_buffer()
		await self._seek(offset, whence)
	
	
	async def tell(self):
		sz = await self._tell()
		
		if self._buffer is None:
			return sz
			
		return sz - len(self._buffer) + self._buffer_start
		
		
	# -----------------------------------------------------------------------------
	#                               Write To Stream
	# -----------------------------------------------------------------------------
	
	async def write(self, buff):
		self._clear_buffer()
		await self._write(buff)
	#!enddef write
	
	
	# -----------------------------------------------------------------------------
	#                               Read From Stream
	# -----------------------------------------------------------------------------
	
	def _can_read(self):
		if not self.readable():
			raise IOException("Read from unreadable stream")
	
	
	async def read(self, count = -1):
		try:
			count = int(count)
		except:
			count = -1
		
		self._can_read()
		
		if self._buffer != None:
			data = self._buffer[self._buffer_start:]
			self._clear_buffer()
			return data
		
		return await self._read(count)
	#!enddef read
	
	
	
	async def readline(self, maxlen = -1):
		self._can_read()
		
		data = bytearray()
		while not await self.eof():
			if self._buffer is None:
				self._buffer = await self._read(self._max_buffer_size)
				
			pos_n = self._buffer.find(b'\n', self._buffer_start)
			if pos_n != -1:
				data.extend(self._buffer[self._buffer_start:pos_n])
				self._buffer_start = pos_n + 1
				break
				
			data.extend(self._buffer[self._buffer_start:])
			self._clear_buffer()
			
		return data
	
	
	
	async def readline_iter(self, maxlen = -1):
		
		class f:
			def __init__(self, stream, maxlen):
				self.stream = stream
				self.maxlen = maxlen
			
			async def __aiter__(self):
				return self
			
			
			async def __anext__(self):
				
				if await self.stream._eof():
					raise StopAsyncIteration
				
				if self.stream._buffer is None:
					self.stream._buffer = await self.stream._read(self._max_buffer_size)
					
				if self.count_readed > self.maxlen and self.maxlen != -1:
					raise EndLineException	
					
				pos_n = self.stream._buffer.find(b'\n', self._buffer_start)
				if pos_n != -1:
					data = self.stream._buffer[self._buffer_start:pos_n]
					self._buffer_start = pos_n + 1
					#self.count_readed += pos_n - cur + 1
					return data
					
				#self.count_readed += end - cur
				data = self.stream._buffer[self._buffer_start:]
				self._clear_buffer()
				
				return data
		
		return f(self, maxlen)
	

#!endclass AbstractStream



class FileStream(AbstractStream):
	
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		
		self._file_name = kwargs.get('file_name')
		self._mode = kwargs.get('mode')
		self._handle = None
		self._fs = kwargs.get('fs')
		
		if self._fs is None:
			self._fs = _local_fs
		
		self._size_hash = 0
		self._pos_hash = 0
		
		self._size_dirty = True
		self._pos_dirty = True
	
	def seekable(self):
		return True
	
	def writable(self):
		return True
	
	def readable(self):
		return True
	
	async def _open(self):
		if self._handle is not None:
			await self.close()
	
		if await self._fs.file_exists(self._file_name):
			self._size_hash = await self._fs.file_size(self._file_name)
			self._handle = await self._fs.file_open(self._file_name, self._mode)
		else:
			self._handle = None
		
		return self._handle is not None
	
	async def _close(self):
		if self._handle is not None:
			await self._fs.file_close(self._handle)
		self._handle = None
	
	async def _read(self, count=-1):
		data = []
		if self._handle is not None:
			data = await self._fs.file_read(self._handle, count)
			self._pos_dirty = True
		return data
	
	async def _write(self, buf):
		if self._handle is not None:
			await self._fs.file_write(self._handle, buf)
			self._pos_dirty = True
			self._size_dirty = True
	
	async def _seek(self, offset, whence):
		pass
	
	async def _eof(self):
		if self._handle is not None:
			pos = await self._tell()
			size = await self._size()
			return pos >= size
		
		return True
		
	async def _flush(self):
		pass
	
	async def _tell(self):
		if self._pos_dirty:
			await self._update_pos()
		return self._pos_hash
	
	async def _size(self):
		if self._size_dirty:
			await self._update_size()
		return self._size_hash
	
	async def _update_pos(self):
		if self._handle is not None:
			self._pos_hash = await self._fs.file_pos(self._handle)
			self._pos_dirty = False
		return self._pos_hash
		
	async def _update_size(self):
		if self._handle is not None:
			self._size_hash = await self._fs.file_size(self._file_name)
			self._size_dirty = False
		return self._size_hash
	
#!endclass FileStream



class QueueStream(AbstractStream):
	
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self._is_eof = False
		self._is_stop = False
		self._read_waiter = None
		self._list = []
		
	
	def seekable(self):
		return True
	
	def writable(self):
		return False
	
	def readable(self):
		return True
	
	
	async def _try_lock_read(self):
		if len(self._list) == 0 and not self._is_stop and not self._is_eof:
			await self._lock_read()
	
	async def _lock_read(self):
		if self._read_waiter is None:
			self._read_waiter = asyncio.futures.Future(loop=self._loop)
		try:
			await self._read_waiter
		finally:
			self._read_waiter = None
	#!enddef
	
	def _unlock_read(self):
		if self._read_waiter is not None:
			self._read_waiter.set_result(None)
		self._read_waiter = None
	#!enddef
	
	
	async def stop(self):
		self._is_stop = True
		self._unlock_read()
		
	async def _open(self):
		return True
	
	async def _close(self):
		self._list = []
		self._is_eof = True
		self._is_stop = True
		self._unlock_read()
	
	async def _read(self, count=-1):
		await self._try_lock_read()
		if len(self._list) == 0:
			return []
		
		data = self._list[0]
		del self._list[0]
		
		return data
	
	def feed_data(self, buf):
		if not self._is_stop:
			self._list.append(buf)
			self._unlock_read()
	
	def feed_flush(self):
		self._unlock_read()
	
	def feed_eof(self):
		self._is_eof = True
		self._unlock_read()
	
	async def _seek(self, offset, whence):
		pass
	
	async def _tell(self):
		return None
	
	async def _size(self):
		return None
	
	async def _eof(self):
		return len(self._list) == 0 and self._is_eof == True
	
	async def eof(self):
		return len(self._list) == 0 and self._is_eof == True
	
	async def _flush(self):
		pass
		
#!endclass QueueStream	