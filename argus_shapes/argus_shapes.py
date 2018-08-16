from __future__ import absolute_import, division, print_function
import os
import six
import copy
import glob
import logging
import pickle

import numpy as np
import pandas as pd

import scipy.interpolate as spi
import scipy.stats as sps

import pulse2percept as p2p

import skimage
import skimage.io as skio
import skimage.filters as skif
import skimage.transform as skit
import skimage.morphology as skimo
import skimage.measure as skime

import sklearn.base as sklb
import sklearn.metrics as sklm
import sklearn.utils as sklu

from .due import due, Doi
from . import imgproc

p2p.console.setLevel(logging.ERROR)

__all__ = ["load_data", "load_subjects", "calc_mean_images",
           "is_singlestim_dataframe", "extract_best_pickle_files"]


# Use duecredit (duecredit.org) to provide a citation to relevant work to
# be cited. This does nothing, unless the user has duecredit installed,
# And calls this with duecredit (as in `python -m duecredit script.py`):
due.cite(Doi("10.1167/13.9.30"),
         description="Template project for small scientific Python projects",
         tags=["reference-implementation"],
         path='argus_shapes')


def load_subjects(fname):
    """Loads subject data

    Subject data is supposed to live in a .csv file with the following columns:
    - `subject_id`: must match the shape data .csv (e.g., 'S1')
    - `second_sight_id`: corresponding identifier (e.g., '11-001')
    - `implant_type_str`: either 'ArgusI' or 'ArgusII'
    - (`implant_x`, `implant_y`): x, y coordinates of array center (um)
    - (`loc_od_x`, `loc_od_y`): x, y coordinates of the optic disc center (deg)
    - (`xmin`, `xmax`): screen width at arm's length (dva)
    - (`ymin`, `ymax`): screen height at arm's length (dva)

    Parameters
    ----------
    fname : str
        Path to .csv file.

    Returns
    -------
    df : pd.DataFrame
        The parsed .csv file loaded as a DataFrame.

    """
    # Make sure all required columns are present:
    df = pd.read_csv(fname, index_col='subject_id')
    has_cols = set(df.columns)
    needs_cols = set(['implant_type_str', 'implant_x', 'implant_y', 'loc_od_x',
                      'loc_od_y', 'xmin', 'xmax', 'ymin', 'ymax'])
    if bool(needs_cols - has_cols):
        err = "The following required columns are missing: "
        err += ", ".join(needs_cols - has_cols)
        raise ValueError(err)

    # Make sure array types are valid:
    if bool(set(df.implant_type_str.unique()) - set(['ArgusI', 'ArgusII'])):
        raise ValueError(("'implant_type_str' must be either 'ArgusI' or "
                          "'ArgusII' for all subjects."))

    # Calculate screen ranges from (xmin, xmax), (ymin, ymax):
    df['xrange'] = pd.Series([(a, b) for a, b in zip(df['xmin'], df['xmax'])],
                             index=df.index)
    df['yrange'] = pd.Series([(a, b) for a, b in zip(df['ymin'], df['ymax'])],
                             index=df.index)

    # Load array type from pulse2percept:
    df['implant_type'] = pd.Series([(p2p.implants.ArgusI if i == 'ArgusI'
                                     else p2p.implants.ArgusII)
                                    for i in df['implant_type_str']],
                                   index=df.index)
    return df.drop(columns=['xmin', 'xmax', 'ymin', 'ymax',
                            'implant_type_str'])


def load_data(fname, subject=None, electrodes=None, amp=None, random_state=42):
    """Loads shuffled shape data

    Shape data is supposed to live in a .csv file with the following columns:
    - `PTS_AMP`: Current amplitude as multiple of threshold current
    - `PTS_ELECTRODE`: Name of the electrode (e.g., 'A1')
    - `PTS_FILE`: Name of the drawing file
    - `PTS_FREQ`: Stimulation frequency (Hz)
    - `PTS_PULSE_DUR`: Stimulation pulse duration (ms)
    - `date`: Date that data was recorded
    - `stim_class`: 'SingleElectrode' or 'MultiElectrode'
    - `subject_id`: must match the subject data .csv (e.g., 'S1')

    If there

    Parameters
    ----------
    fname : str
        Path to .csv file.
    subject : str or None, default: None
        Only load data from a particular subject. Set to None to load data from
        all subjects.
    electrodes : list or None, default: None
        Only load data from a particular set of electrodes. Set to None to load
        data from all electrodes
    amp : float or None, default: None
        Only load data with a particular current amplitude. Set to None to load
        data with all current amplitudes.
    random_state : int or None, default: 42
        Seed for the random number generator. Set to None to prevent shuffling.

    Returns
    -------
    df : pd.DataFrame
        The parsed .csv file loaded as a DataFrame, optionally with shuffled
        rows.

    """
    # Make sure .csv file has all necessary columns:
    data = pd.read_csv(fname)
    has_cols = set(data.columns)
    needs_cols = set(['PTS_AMP', 'PTS_FILE', 'PTS_FREQ', 'PTS_PULSE_DUR',
                      'date', 'stim_class', 'subject_id'])
    if bool(needs_cols - has_cols):
        err = "The following required columns are missing: "
        err += ", ".join(needs_cols - has_cols)
        raise ValueError(err)

    # Only load data from a particular subject:
    if subject is not None:
        data = data[data.subject_id == subject]

    # Only load data from a particular set of electrodes:
    is_singlestim = is_singlestim_dataframe(data)
    if electrodes is not None:
        if not isinstance(electrodes, (list, np.ndarray)):
            raise ValueError("`electrodes` must be a list or NumPy array")
        idx = np.zeros(len(data), dtype=np.bool)
        if is_singlestim:
            for e in electrodes:
                idx = np.logical_or(idx, data.PTS_ELECTRODE == e)
        else:
            for e in electrodes:
                idx = np.logical_or(idx, data.PTS_ELECTRODE1 == e)
                idx = np.logical_or(idx, data.PTS_ELECTRODE2 == e)
        data = data[idx]

    # Only load data with a particular current amplitude:
    if amp is not None:
        data = data[np.isclose(data.PTS_AMP, amp)]

    # Shuffle data if random seed is set:
    if random_state is not None:
        data = sklu.shuffle(data, random_state=random_state)

    # Build feature and target matrices:
    features = []
    targets = []
    for _, row in data.iterrows():
        # Extract shape descriptors from phosphene drawing:
        if pd.isnull(row['PTS_FILE']):
            img = np.zeros((10, 10))
        else:
            try:
                img = skio.imread(os.path.join(os.path.dirname(fname),
                                               row['PTS_FILE']), as_gray=True)
                img = skimage.img_as_float(img)
            except FileNotFoundError:
                try:
                    img = skio.imread(row['PTS_FILE'], as_gray=True)
                except FileNotFoundError:
                    s = ('Column "PTS_FILE" must either specify an absolute '
                         'path or a relative path that starts in the '
                         'directory of `fname`.')
                    raise FileNotFoundError(s)
        props = imgproc.calc_shape_descriptors(img)
        if is_singlestim:
            target = {'image': img, 'electrode': row['PTS_ELECTRODE']}
        else:
            target = {'image': img, 'electrode1': row['PTS_ELECTRODE1'],
                      'electrode2': row['PTS_ELECTRODE2']}
        target.update(props)
        targets.append(target)

        # Save additional attributes:
        feat = {
            'subject': row['subject_id'],
            'filename': row['PTS_FILE'],
            'img_shape': img.shape,
            'stim_class': row['stim_class'],
            'amp': row['PTS_AMP'],
            'freq': row['PTS_FREQ'],
            'pdur': row['PTS_PULSE_DUR'],
            'date': row['date']
        }
        if is_singlestim:
            feat.update({'electrode': row['PTS_ELECTRODE']})
        else:
            feat.update({'electrode1': row['PTS_ELECTRODE1'],
                         'electrode2': row['PTS_ELECTRODE2']})
        features.append(feat)
    features = pd.DataFrame(features, index=data.index)
    targets = pd.DataFrame(targets, index=data.index)
    return features, targets


def is_singlestim_dataframe(data):
    """Determines whether a DataFrame contains single or multi electrode stim

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame containing the shape data

    Returns
    -------
    is_singlestim : bool
        Whether DataFrame contains single stim (True) or not (False).
    """
    if not np.any([c in data.columns for c in ['PTS_ELECTRODE', 'electrode',
                                               'PTS_ELECTRODE1', 'electrode1',
                                               'PTS_ELECTRODE2',
                                               'electrode2']]):
        raise ValueError(('Incompatible csv file "%s". Must contain one of '
                          'these columns: PTS_ELECTRODE, PTS_ELECTRODE1, '
                          'PTS_ELECTRODE2, electrode, electrode1, electrode2'))
    is_singlestim = (('PTS_ELECTRODE' in data.columns or
                      'electrode' in data.columns) and
                     ('PTS_ELECTRODE1' not in data.columns or
                      'electrode1' in data.columns) and
                     ('PTS_ELECTRODE2' not in data.columns or
                      'electrode2' in data.columns))
    return is_singlestim


def _calcs_mean_image(Xy, groupcols, thresh=True, max_area=1.5):
    """Private helper function to calculate a mean image"""
    for col in groupcols:
        assert len(Xy[col].unique()) == 1

    is_singlestim = is_singlestim_dataframe(Xy)
    if is_singlestim:
        assert len(Xy.electrode.unique()) == 1
    else:
        assert len(Xy.electrode1.unique()) == 1
        assert len(Xy.electrode2.unique()) == 1

    # Calculate mean image
    images = Xy.image
    img_avg = None

    for img in images:
        if img_avg is None:
            img_avg = np.zeros_like(img, dtype=float)
        img_avg += imgproc.center_phosphene(img)

    # Adjust to [0, 1]
    if img_avg.max() > 0:
        img_avg /= img_avg.max()
    # Threshold if required:
    if thresh:
        img_avg = imgproc.get_thresholded_image(img_avg, thresh='otsu')
    # Move back to its original position:
    img_avg = imgproc.center_phosphene(img_avg, center=(np.mean(Xy.y_center),
                                                        np.mean(Xy.x_center)))

    # Calculate shape descriptors:
    descriptors = imgproc.calc_shape_descriptors(img_avg)

    # Compare area of mean image to the mean of trial images: If smaller than
    # some fraction, skip:
    if descriptors['area'] > max_area * np.mean(Xy.area):
        return None, None

    # Remove ambiguous (trial-related) parameters:
    if is_singlestim:
        target = {'electrode': Xy.electrode.unique()[0],
                  'image': img_avg}
    else:
        target = {'electrode1': Xy.electrode1.unique()[0],
                  'electrode2': Xy.electrode2.unique()[0],
                  'image': img_avg}
    target.update(descriptors)

    feat = {'img_shape': img_avg.shape}
    for col in groupcols:
        feat[col] = Xy[col].unique()[0]

    return feat, target


def calc_mean_images(Xraw, yraw, groupcols=['subject', 'amp', 'electrode'],
                     thresh=True, max_area=1.5):
    """Extract mean images on an electrode from all raw trial drawings

    Parameters
    ----------
    Xraw: pd.DataFrame
        Feature matrix, raw trial data
    yraw: pd.DataFrame
        Target values, raw trial data
    thresh: bool, optional, default: True
        Whether to binarize the averaged image.
    max_area: float, optional, default: 2
        Skip if mean image has area larger than a factor `max_area`
        of the mean of the individual images. A large area of the mean
        image indicates poor averaging: instead of maintaining area,
        individual nonoverlapping images are added.

    Returns
    =======
    Xout: pd.DataFrame
        Feature matrix, single entry per electrode
    yout: pd.DataFrame
        Target values, single entry per electrode
    """
    is_singlestim = is_singlestim_dataframe(yraw)
    if is_singlestim:
        Xy = pd.concat((Xraw, yraw.drop(columns='electrode')), axis=1)
    else:
        Xy = pd.concat((Xraw, yraw.drop(columns=['electrode1', 'electrode2'])),
                       axis=1)
    assert np.allclose(Xy.index, Xraw.index)

    Xout = []
    yout = []
    for _, data in Xy.groupby(groupcols):
        f, t = _calcs_mean_image(data, groupcols, thresh=thresh,
                                 max_area=max_area)
        if f is not None and t is not None:
            Xout.append(f)
            yout.append(t)

    return pd.DataFrame(Xout), pd.DataFrame(yout)


def _extracts_score_from_pickle(file, col_score, col_groupby):
    """Private helper function to extract the score from a pickle file"""
    _, _, _, specifics = pickle.load(open(file, 'rb'))
    assert np.all([g in specifics for g in col_groupby])
    assert col_score in specifics
    params = specifics['optimizer'].get_params()
    # TODO: make this work for n_folds > 1
    row = {
        'file': file,
        'greater_is_better': params['estimator__greater_is_better'],
        col_score: specifics[col_score][0]
    }
    for g in col_groupby:
        row.update({g: specifics[g]})
    return row


def extract_best_pickle_files(results_dir, col_score, col_groupby):
    """Finds the fitted models with the best scores

    For all pickle files in a directory (supposedly containing the results of
    different parameter fits), this function returns a list of pickle files
    that have the best score.

    The `col_groupby` argument can be used to find the best scores for each
    cross-validation fold (e.g., group by ['electrode', 'idx_fold']).

    Parameters
    ----------
    results_dir : str
        Path to results directory.
    col_score : str
        Name of the DataFrame column that contains the score.
    col_groupby : list
        List of columns by which to group the DataFrame
        (e.g., ['electrode', 'idx_fold']).

    Returns
    -------
    files : list
        A list of pickle files with the best scores.

    """
    # Extract relevant info from pickle files:
    pickle_files = np.sort(glob.glob(os.path.join(results_dir, '*.pickle')))
    data = p2p.utils.parfor(_extracts_score_from_pickle, pickle_files,
                            func_args=[col_score, col_groupby])
    # Convert to DataFrame:
    df = pd.DataFrame(data)
    # Make sure all estimator use the same scoring logic:
    assert np.isclose(np.var(df.greater_is_better), 0)
    # Find the rows that minimize/maximize the score:
    if df.loc[0, 'greater_is_better']:
        # greater score is better: maximize
        res = df.loc[df.groupby(col_groupby)[col_score].idxmax()]
    else:
        # greater is worse: minimize
        res = df.loc[df.groupby(col_groupby)[col_score].idxmin()]
    # Return list of files:
    return res.file.tolist()
