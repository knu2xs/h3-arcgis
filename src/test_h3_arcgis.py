import math
from pathlib import Path

import arcpy
from ba_tools import data
import pandas as pd
import numpy as np

from h3 import h3
from itertools import chain
import json
import os
from pathlib import Path
import sys
from copy import deepcopy
import pytest

from arcgis.features import GeoAccessor
from arcgis.geometry import Geometry
import pandas as pd

project_parent = Path(__file__).absolute().parent.parent

data_dir = project_parent/'data'

data_raw = data_dir/'raw'
data_int = data_dir/'interim'
data_out = data_dir/'processed'

gdb_raw = data_raw/'raw.gdb'
gdb_int = data_int/'interim.gdb'
gdb_out = data_out/'processed.gdb'

pth_bp = gdb_int/'block_points'

# import the project package from the project package path
sys.path.append(str(project_parent/'src'))
from h3_arcgis import *


@pytest.fixture
def df_bp():
    df_bp = GeoAccessor.from_featureclass(str(pth_bp))
    df_bp = df_bp[['FIPS', 'SHAPE', 'HH_C']].copy()
    df_bp.columns = ['FIPS', 'SHAPE', 'HouseholdCount']
    return df_bp


def test_get_nonoverlapping_h3_hexbins_for_points_weighted(df_bp):
    df_ids = get_nonoverlapping_h3_hexbins_for_points(
        spatially_enabled_dataframe=df_bp,
        h3_minimum=5,
        h3_maximum=9,
        minimum_threshold_value=5000,
        weighting_column='HouseholdCount'
    )
    assert(isinstance(df_ids, pd.DataFrame))
