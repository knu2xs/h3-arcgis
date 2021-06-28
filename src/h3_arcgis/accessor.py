from arcgis import GeoAccessor
from arcgis.features.geo._internals import register_dataframe_accessor
import pandas as pd
import swifter

from .main import get_esri_geometry_for_h3_id

@register_dataframe_accessor('h3')
class H3Accessor:
    """
    DataFrame accessor facilitating working with H3 and Spatially Enabled Dataframes.
    """
    def __init__(self, obj):
        self._data = obj
        self._index = obj.index

    def get_esri_geometry(self, h3_id_column: str = 'h3_id') -> pd.DataFrame:
        """
        Add Esri polygon geometries for the H3 ID's to the dataframe.

        .. code:: python

            from h3_arcgis import H3Accessor
            import pandas as pd

            df = pd.read_parquet(r'path/to/table')

            sedf = df.h3.get_esri_geometry('h3_id_col')

        :param h3_id_column: Column containing H3 ID's.

        :returns: Spatially Enabled DataFrame with hexagon polygons.
        """
        # reference the dataframe for brevity
        df = self._data

        # get the polygon geometries for each H3 ID and save to new SHAPE column
        df['SHAPE'] = df[h3_id_column].swifter.apply(lambda val: get_esri_geometry_for_h3_id(val))

        # tell the dataframe where the geometry is
        df.spatial.set_geometry('SHAPE')

        return df
