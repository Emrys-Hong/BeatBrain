import os
import re
import glob
import time
import enum
import numpy as np
import librosa
import librosa.display
import soundfile as sf
from pathlib import Path
from natsort import natsorted
from colorama import Fore
from tqdm import tqdm
from PIL import Image

from . import settings


class DataType(enum.Enum):
    AUDIO = 1
    NUMPY = 2
    ARRAY = 2
    IMAGE = 3
    UNKNOWN = 4
    AMBIGUOUS = 5
    ERROR = 6


SUPPORTED_EXTENSIONS = {
    DataType.AUDIO: ['wav', 'flac', 'mp3', 'ogg'],
    DataType.NUMPY: ['npy', 'npz'],
    DataType.IMAGE: ['tiff']
}


def get_data_type(path, raise_exception=False):
    """
    Given a file or directory, return the (homogeneous) data type contained in that path.

    Args:
        path: Path at which to check the data type.
        raise_exception: Whether to raise an exception on unknown or ambiguous data types.

    Returns:
        DataType: The type of data contained at the given path (Audio, Numpy, or Image)

    Raises:
        ValueError: If `raise_exception` is True, the number of matched data types is either 0 or >1.
    """
    print(f"Checking input type(s)...")
    found_types = set()
    path = Path(path)
    files = []
    if path.is_file():
        files = [path]
    elif path.is_dir():
        files = filter(Path.is_file, path.rglob('*'))
    for f in files:
        for dtype, exts in SUPPORTED_EXTENSIONS.items():
            suffix = f.suffix[1:]
            if suffix in exts:
                found_types.add(dtype)
    if len(found_types) == 0:
        dtype = DataType.UNKNOWN
        if raise_exception:
            raise ValueError(f"Unknown source data type. No known file types we matched.")
    elif len(found_types) == 1:
        dtype = found_types.pop()
    else:
        dtype = DataType.AMBIGUOUS
        if raise_exception:
            raise ValueError(f"Ambiguous source data type. The following types were matched: {found_types}")
    print(f"Determined input type to be {Fore.CYAN}'{dtype.name}'{Fore.RESET}")
    return dtype


def spec_to_chunks(spec, chunk_size, truncate):
    """
    Split a numpy array along the x-axis into fixed-length chunks

    Args:
        spec (np.ndarray):
        chunk_size (int):
        truncate (bool):

    Returns:
        list: A list of numpy arrays of equal size
    """
    if spec.shape[-1] >= chunk_size:
        remainder = spec.shape[-1] % chunk_size
        if truncate:
            spec = spec[:, :-remainder]
        else:
            spec = np.pad(spec, ((0, 0), (0, chunk_size - remainder)), mode='constant')
        chunks = np.split(spec, spec.shape[-1] // chunk_size, axis=1)
    else:
        chunks = [spec]
    return chunks


def convert_audio_to_numpy(inp, out_dir, sr=settings.SAMPLE_RATE, offset=settings.AUDIO_OFFSET,
                           duration=settings.AUDIO_DURATION, res_type=settings.RESAMPLE_TYPE,
                           n_fft=settings.N_FFT, hop_length=settings.HOP_LENGTH,
                           n_mels=settings.N_MELS, chunk_size=settings.CHUNK_SIZE,
                           truncate=settings.TRUNCATE, skip=0):
    inp = Path(inp)
    out_dir = Path(out_dir)
    if not inp.exists():
        raise ValueError(f"Input must be a valid file or directory. Got '{inp}'")
    elif inp.is_dir():
        paths = natsorted(filter(Path.is_file, inp.rglob('*')))
    else:
        paths = [inp]
    print(f"Converting files in {Fore.YELLOW}'{inp}'{Fore.RESET} to Numpy arrays...")
    print(f"Arrays will be saved in {Fore.YELLOW}'{out_dir}'{Fore.RESET}\n")
    for i, path in enumerate(tqdm(paths, desc="Converting")):
        if i < skip:
            continue
        tqdm.write(f"Converting {Fore.YELLOW}'{path}'{Fore.RESET}...")
        audio, sr = librosa.load(str(path), sr=sr, offset=offset, duration=duration, res_type=res_type)
        spec = librosa.feature.melspectrogram(audio, sr=sr, n_fft=n_fft, hop_length=hop_length, n_mels=n_mels)
        spec = librosa.power_to_db(spec, top_db=settings.TOP_DB, ref=np.max)
        spec = spec - spec.min()
        spec = spec / np.abs(spec).max()
        chunks = spec_to_chunks(spec, chunk_size, truncate)
        output = out_dir.joinpath(path.relative_to(inp))
        output = output.parent.joinpath(output.stem)
        output.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(output, *chunks)


# TODO: Implement
def convert_image_to_numpy(inp, out_dir, flip=settings.IMAGE_FLIP, skip=0):
    pass


def convert_audio_to_image(inp, out_dir, sr=settings.SAMPLE_RATE, offset=settings.AUDIO_OFFSET,
                           duration=settings.AUDIO_DURATION, res_type=settings.RESAMPLE_TYPE,
                           n_fft=settings.N_FFT, hop_length=settings.HOP_LENGTH, n_mels=settings.N_MELS,
                           chunk_size=settings.CHUNK_SIZE, truncate=settings.TRUNCATE,
                           flip=settings.IMAGE_FLIP, skip=0):
    inp = Path(inp)
    out_dir = Path(out_dir)
    if not inp.exists():
        raise ValueError(f"Input must be a valid file or directory. Got '{inp}'")
    elif inp.is_dir():
        paths = natsorted(filter(Path.is_file, inp.rglob('*')))
    else:
        paths = [inp]
    print(f"Converting files in {Fore.YELLOW}'{inp}'{Fore.RESET} to images...")
    print(f"Images will be saved in {Fore.YELLOW}'{out_dir}'{Fore.RESET}\n")
    for i, path in enumerate(tqdm(paths, desc="Converting")):
        if i < skip:
            continue
        tqdm.write(f"Converting {Fore.YELLOW}'{path}'{Fore.RESET}...")
        audio, sr = librosa.load(str(path), sr=sr, offset=offset, duration=duration, res_type=res_type)
        spec = librosa.feature.melspectrogram(audio, sr=sr, n_fft=n_fft, hop_length=hop_length, n_mels=n_mels)
        spec = librosa.power_to_db(spec, ref=np.max)
        spec = spec - spec.min()
        spec = spec / np.abs(spec).max()
        chunks = spec_to_chunks(spec, chunk_size, truncate)
        if flip:
            chunks = [chunk[::-1] for chunk in chunks]
        tqdm.write(f"Converting {Fore.YELLOW}'{path}'{Fore.RESET}...")
        output = out_dir.joinpath(path.relative_to(inp))
        output = output.parent.joinpath(output.stem)
        output.mkdir(parents=True, exist_ok=True)
        for j, chunk in enumerate(chunks):
            image = Image.fromarray(chunk, mode='F')
            image.save(output.joinpath(f"{j}.tiff"))


def convert_numpy_to_image(inp, out_dir, flip=settings.IMAGE_FLIP, skip=0):
    inp = Path(inp)
    out_dir = Path(out_dir)
    if not inp.exists():
        raise ValueError(f"Input must be a valid file or directory. Got '{inp}'")
    elif inp.is_dir():
        paths = natsorted(filter(Path.is_file, inp.rglob('*')))
    else:
        paths = [inp]
    print(f"Converting files in {Fore.YELLOW}'{inp}'{Fore.RESET} to images...")
    print(f"Images will be saved in {Fore.YELLOW}'{out_dir}'{Fore.RESET}\n")
    for i, path in enumerate(tqdm(paths, desc="Converting")):
        if i < skip:
            continue
        tqdm.write(f"Converting {Fore.YELLOW}'{path}'{Fore.RESET}...")
        output = out_dir.joinpath(path.relative_to(inp))
        output = output.parent.joinpath(output.stem)
        output.mkdir(parents=True, exist_ok=True)
        with np.load(path) as npz:
            for j, chunk in enumerate(npz.values()):
                if flip:
                    chunk = chunk[::-1]
                image = Image.fromarray(chunk, mode='F')
                image.save(output.joinpath(f"{j}.tiff"))


# TODO: Optimize
def convert_numpy_to_audio(inp, out_dir, sr=settings.SAMPLE_RATE, n_fft=settings.N_FFT,
                           hop_length=settings.HOP_LENGTH, fmt=settings.AUDIO_FORMAT,
                           offset=settings.AUDIO_OFFSET, duration=settings.AUDIO_DURATION, skip=0):
    inp = Path(inp)
    out_dir = Path(out_dir)
    if not inp.exists():
        raise ValueError(f"Input must be a valid file or directory. Got '{inp}'")
    elif inp.is_dir():
        paths = natsorted(filter(Path.is_file, inp.rglob('*')))
    else:
        paths = [inp]
    print(f"Converting files in {Fore.YELLOW}'{inp}'{Fore.RESET} to audio...")
    print(f"Images will be saved in {Fore.YELLOW}'{out_dir}'{Fore.RESET}\n")
    for i, path in enumerate(tqdm(paths, desc="Converting")):
        if i < skip:
            continue
        tqdm.write(f"Converting {Fore.YELLOW}'{path}'{Fore.RESET}...")
        output = out_dir.joinpath(path.relative_to(inp))
        output = output.parent.joinpath(output.name).with_suffix(f'.{fmt}')
        output.parent.mkdir(parents=True, exist_ok=True)
        with np.load(path) as npz:
            chunks = list(npz.values())
        spec = np.concatenate(chunks, axis=-1)
        spec = librosa.db_to_power(settings.TOP_DB * (spec - 1), ref=50000)
        audio = librosa.feature.inverse.mel_to_audio(spec, sr=sr, n_fft=n_fft, hop_length=hop_length)
        sf.write(output, audio, sr)


# TODO: Implement
def convert_image_to_audio(inp, out_dir, sr=settings.SAMPLE_RATE, n_fft=settings.N_FFT,
                           hop_length=settings.HOP_LENGTH, fmt=settings.AUDIO_FORMAT,
                           offset=settings.AUDIO_OFFSET, duration=settings.AUDIO_DURATION,
                           flip=settings.IMAGE_FLIP, skip=0):
    inp = Path(inp)
    out_dir = Path(out_dir)
    if not inp.exists():
        raise ValueError(f"Input must be a valid file or directory. Got '{inp}'")
    elif inp.is_dir():
        paths = filter(Path.is_file, inp.rglob('*'))
        paths = natsorted({p.parent for p in paths})
    else:
        paths = [inp]
    print(f"Converting files in {Fore.YELLOW}'{inp}'{Fore.RESET} to images...")
    print(f"Images will be saved in {Fore.YELLOW}'{out_dir}'{Fore.RESET}\n")
    for i, path in enumerate(tqdm(paths, desc="Converting")):
        if i < skip:
            continue
        print(path)


# region Functions used by the `click` CLI
def convert_to_numpy(inp, out_dir, sr=settings.SAMPLE_RATE, offset=settings.AUDIO_OFFSET,
                     duration=settings.AUDIO_DURATION, res_type=settings.RESAMPLE_TYPE,
                     n_fft=settings.N_FFT, hop_length=settings.HOP_LENGTH,
                     n_mels=settings.N_MELS, chunk_size=settings.CHUNK_SIZE, truncate=settings.TRUNCATE,
                     flip=settings.IMAGE_FLIP, skip=0):
    dtype = get_data_type(inp, raise_exception=True)
    if dtype == DataType.AUDIO:
        return convert_audio_to_numpy(inp, out_dir, sr=sr, offset=offset, duration=duration, res_type=res_type,
                                      n_fft=n_fft, hop_length=hop_length, n_mels=n_mels,
                                      chunk_size=chunk_size, truncate=truncate, skip=skip)
    elif dtype == DataType.IMAGE:
        return convert_image_to_numpy(inp, out_dir, flip=flip, skip=skip)


def convert_to_image(inp, out_dir, sr=settings.SAMPLE_RATE, offset=settings.AUDIO_OFFSET,
                     duration=settings.AUDIO_DURATION, res_type=settings.RESAMPLE_TYPE, n_fft=settings.N_FFT,
                     hop_length=settings.HOP_LENGTH, chunk_size=settings.CHUNK_SIZE,
                     truncate=settings.TRUNCATE, flip=settings.IMAGE_FLIP, skip=0):
    dtype = get_data_type(inp, raise_exception=True)
    if dtype == DataType.AUDIO:
        return convert_audio_to_image(inp, out_dir, sr=sr, offset=offset, duration=duration, res_type=res_type,
                                      n_fft=n_fft, hop_length=hop_length, chunk_size=chunk_size, truncate=truncate,
                                      flip=flip, skip=skip)
    elif dtype == DataType.NUMPY:
        return convert_numpy_to_image(inp, out_dir, flip=flip, skip=skip)


def convert_to_audio(inp, out_dir, sr=settings.SAMPLE_RATE, n_fft=settings.N_FFT,
                     hop_length=settings.HOP_LENGTH, fmt=settings.AUDIO_FORMAT,
                     offset=settings.AUDIO_OFFSET, duration=settings.AUDIO_DURATION,
                     flip=settings.IMAGE_FLIP, skip=0):
    dtype = get_data_type(inp, raise_exception=True)
    if dtype == DataType.NUMPY:
        return convert_numpy_to_audio(inp, out_dir, sr=sr, n_fft=n_fft, hop_length=hop_length,
                                      fmt=fmt, offset=offset,
                                      duration=duration, skip=skip)
    elif dtype == DataType.IMAGE:
        return convert_image_to_audio(inp, out_dir, sr=sr, n_fft=n_fft, hop_length=hop_length,
                                      fmt=fmt, offset=offset,
                                      duration=duration, flip=flip, skip=skip)
# endregion
