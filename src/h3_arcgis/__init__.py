from itertools import chain
import json
import os
from pathlib import Path

from arcgis.features import GeoAccessor
from arcgis.geometry import Geometry, Polygon
from arcgis.gis import GIS
from copy import deepcopy
from dotenv import load_dotenv, find_dotenv
from h3 import h3
import pandas as pd
import swifter

# what we're going to tell the world about
__all__ = ['get_unique_h3_ids_for_aoi', 'get_esri_geometry_for_h3_id', 'get_esri_geometry_for_h3_id',
           'get_h3_hex_dataframe_from_h3_id_lst', 'get_h3_hex_for_aoi', 'get_nonoverlapping_h3_hexbins_for_points']


def _preprocess_sdf_for_h3(orig_df: pd.DataFrame) -> pd.DataFrame:
    """
    Since H3 cannot handle multipart geometries, break apart any potential multipart geometries into
    discrete rows for subsequent analysis.
    :param orig_df: Spatially enabled dataframe delineating the area of interest.
    :returns: Spatially enabled dataframe of hexagons covering the area of interest.
    """
    # create a new dataframe to hold single part geometric features
    new_df = pd.DataFrame(columns=orig_df.columns)

    # for every row explode out any multipart geometric features since Uber H3 cannot hadle multipart
    for x, row in orig_df.iterrows():
        geom = row['SHAPE']
        for ring in geom.rings:
            new_geom = deepcopy(geom)
            new_geom.rings = [ring]
            new_row = deepcopy(row)
            new_row['SHAPE'] = new_geom
            new_df = new_df.append(new_row)

    # reset the index and get the geometry working
    new_df.reset_index(drop=True, inplace=True)
    new_df.spatial.set_geometry('SHAPE')

    return new_df


def get_unique_h3_ids_for_aoi(orig_df: pd.DataFrame, hex_level: int = 9) -> list:
    """
    Given an area of interest, create Uber H3 hexagons covering the area of interest.
    :param orig_df: Spatially enabled dataframe delineating the area of interest.
    :param hex_level: Integer indicating the desired H3 level defining output hexagon tessellation resolution.
    :returns: List of unique Uber H3 indices whose centroids fall within the area of interest.
    """
    # explode all the multipart geometric features into discrete geometric features
    expl_df = _preprocess_sdf_for_h3(orig_df)

    # create a feature set of all the exploded features
    fs_expl = expl_df.spatial.to_featureset()

    # extract the features as geojson from the feature set
    fs_geojson = json.loads(fs_expl.to_geojson)
    geojson_feat_lst = fs_geojson['features']

    def _get_h3_ids(geojson_feat):
        """helper function to get the h3 id's for a single geometry"""

        # pull the geometry out of the geojson feature
        geojson_aoi = geojson_feat['geometry']

        # get a list of all the hex id's within the area of interest
        return h3.polyfill(geojson_aoi, hex_level, geo_json_conformant=True)

    # get a list of lists containing all the h3 id's contained in the area of interest
    h3_ids_lst = [_get_h3_ids(feat) for feat in geojson_feat_lst]

    # combine all the id's and use a set to eliminate any duplicates
    h3_ids = set(chain.from_iterable(h3_ids_lst))

    if len(h3_ids) == 0:
        raise Exception(f'The resolution provided, H3 level {hex_level}, is too coarse to return any results.'
                        f' Please select a finer level of detail, say level {hex_level + 1}, and see if that works '
                        'any better.')

    return list(h3_ids)


def get_esri_geometry_for_h3_id(h3_id: str) -> Polygon:
    """
    Convert an Uber H3 id to an ArcGIS Python API Polygon Geometry object.
    :param h3_id: String Uber H3 id.
    :return: ArcGIS Python API Polygon Geometry object
    """
    # get a list of coordinate rings for the hex id's
    coord_lst = [h3.h3_to_geo_boundary(h3_id, geo_json=True)]

    # creat a geometry object using this geometry list
    return Polygon({"type": "Polygon", "coordinates": coord_lst,
                     'spatialReference': {'wkid': 4326, 'latestWkid': 4326}})


def get_h3_spatially_enabled_dataframe(df: pd.DataFrame, h3_address_column: str) -> pd.DataFrame:
    """
    Create a spatially enabled dataframe with geometry created from the h3 addresses in a column.
    :param df: Pandas dataframe.
    :param h3_address_column: Column to be used for calculating the h3 geometry.
    :return: Spatialy enabled dataframe.
    """
    if df[h3_address_column].isnull().any():
        raise Exception(f'There appear to be missing values in the specified H3 column, {h3_address_column}.')

    df['SHAPE'] = df[h3_address_column].swifter.apply(lambda h3_id: get_esri_geometry_for_h3_id(h3_id))
    df.spatial.set_geometry('SHAPE')

    return df



def get_h3_hex_dataframe_from_h3_id_lst(h3_id_lst: list) -> pd.DataFrame:
    """
    From a list of H3 id's, return a spatially enabled dataframe with all the geometries.
    :param h3_id_lst: String list of H3 identifiers.
    :return: Spatially enabled dataframe of hexagons.
    """
    # create a list of geometries corresponding to the hex id's
    geom_lst = [get_esri_geometry_for_h3_id(hex_id) for hex_id in h3_id_lst]

    # zip together the hex id's and geometries into a dataframe, and spatially enable it
    df = pd.DataFrame(zip(h3_id_lst, geom_lst), columns=['h3_id', 'SHAPE'])
    df.spatial.set_geometry('SHAPE')

    return df


def get_h3_hex_for_aoi(orig_df: pd.DataFrame, hex_level: int = 9) -> pd.DataFrame:
    """
    Given an area of interest, create Uber H3 hexagons covering the area of interest.
    :param orig_df: Spatially enabled dataframe delineating the area of interest.
    :return: Spatially enabled dataframe of hexagons covering the area of interest.
    """
    h3_ids = get_unique_h3_ids_for_aoi(orig_df, hex_level)
    df = get_h3_hex_dataframe_from_h3_id_lst(h3_ids)
    return df


# AGGREGATION SECTION

# consistent column names - may parameterize later, but this works for now...
h3_id_col = 'h3_id'
h3_lvl_col = 'h3_lvl'
h3_lvl_orig_col = 'h3_orig'


def _h3_col(h3_lvl):
    """Make it easy and reporducable to create a h3 column"""
    return f'h3_{h3_lvl:02d}'


def _get_h3_range_lst(h3_min, h3_max):
    """Helper to get H3 range list."""
    return list(range(h3_min, h3_max + 1))


def _get_h3_col_lst_from_df(df):
    """Helper get H3 columns for dataframe."""
    return [col for col in df.columns if col.startswith('h3_') and col[-2:].isnumeric()]


def _get_h3_range_lst_from_df(df):
    """Helper to get H3 range list from column names."""
    return [int(col[-2:]) for col in _get_h3_col_lst_from_df(df)]


def add_h3_ids_to_points(df: pd.DataFrame, h3_max: int, h3_min: int) -> pd.DataFrame:
    """Add Uber H3 ids to the point geometries in a Spatially Enabled DataFrame.
    :param df: Spatially Enabled DataFrame with point geometries to be aggregated.
    :param h3_max: Integer maximum H3 grid level defining the samllest geographic hex area - must be larger than the minimum.
    :param h3_min: Integer minimum H3 grid level defining the largest geograhpic hex area - must be smaller than the maximum.
    :return: Pandas DataFrame with Uber H3 ids added for all the resolutions betwen teh maximum and minimum.
    """
    assert h3_max > h3_min

    # get a list of zoom levels and ensure the H3 levels are sorted from highest to lowest resolution
    h3_lvl_lst = _get_h3_range_lst(h3_min, h3_max)
    h3_lvl_lst.sort(reverse=True)

    # calculate the highest resolution H3 id for each location
    first_level = h3_lvl_lst[0]
    df[_h3_col(first_level)] = df.SHAPE.swifter.apply(
        lambda geom: h3.geo_to_h3(geom.centroid[1], geom.centroid[0], first_level))

    # use the highest resolution H3 id to get progressivley lower resolution H3 id's
    for h3_lvl in h3_lvl_lst[1:]:
        df[_h3_col(h3_lvl)] = df[_h3_col(first_level)].swifter.apply(
            lambda first_val: h3.h3_to_parent(first_val, h3_lvl))

    return df


def get_h3_ids_by_count(df: pd.DataFrame, min_count: int, count_column: str = None) -> pd.DataFrame:
    """Assign a H3 id to each point based on the H3 count in increasingly resolution H3 hexagons. If not enough present, the points
    for the summary tesselation cell will not be retained.
    :param df: Pandas DataFrame with properly formatted columns delineating the Uber H3 ids at varying resolutions.
    :param min_count: The minimum count to consider for retaining the H3 id.
    :param count_column: Column containing the value summed to create a count for threshold evaluation.
    """
    # provide default
    count_column = 'count' if count_column is None else count_column

    # get the levels from the column names
    h3_lvl_lst = _get_h3_range_lst_from_df(df)

    # ensure the hex levels are sorted in order (larger to smaller area)
    h3_lvl_lst.sort()

    # iterate the hex levels
    for h3_lvl in h3_lvl_lst:

        # create the hex column name string
        h3_col = _h3_col(h3_lvl)

        # if a count column is provided, use this for aggregation
        if count_column == 'count':
            h3_id_cnt = df[h3_col].value_counts()

        # otherwise, just get a point count
        else:
            h3_id_cnt = df.groupby(h3_col).sum()[count_column]

        # if the count for the hex id is greater than the minimum, assign an id - critical for PII
        h3_id_lst = h3_id_cnt[h3_id_cnt > min_count].index.values

        # create a slice expression for just records matching the saved hex ids
        df_slice = df[h3_col].isin(h3_id_lst)

        # save the hex id's in the final column for the values exceeding the threshold
        df.loc[df_slice, h3_id_col] = df[df_slice][h3_col]
        df.loc[df_slice, h3_lvl_col] = h3_lvl

        # Note the hex level
        df.loc[df_slice, h3_lvl_orig_col] = h3_lvl

    return df


def remove_overlapping_h3_ids(df: pd.DataFrame) -> pd.DataFrame:
    """Remove all overlapping H3 ids. This assigns points to a larger parent H3 region if other points in this
    parent hexagon were not dense enough to populate the other six participating hexbins.
    :param df: Pandas DataFrame with standard schema produced by earlier steps.
    :return: Pandas DataFrame ready to create geometries and counts with.
    """
    # get the levels from the column names
    h3_lvl_lst = _get_h3_range_lst_from_df(df)

    # ensure reverse sorting, so moving from smaller to larger h3 hexbins
    h3_lvl_lst.sort(reverse=True)

    # get a list of all h3 id's for comparison later
    h3_id_lst = df[h3_id_col].unique()

    # reverse the sorting so it goes from smallest area to largest
    for h3_lvl in h3_lvl_lst[:-1]:

        # variable storing the number of zoom levels to iterate up
        zoom_range = h3_lvl - h3_lvl_lst[-1]

        # now, jump up the zoom levels to ensure checking to the top of the resolutions
        for idx in range(0, zoom_range + 1):

            # get the name of the column at the zoom level
            nxt_h3_lvl = h3_lvl - idx
            nxt_h3_col = _h3_col(nxt_h3_lvl)

            # create a filter to identify only the records where the next zoom level, the containing h3,
            # is also being used
            df_slice = df[nxt_h3_col].isin(h3_id_lst)

            # if nothing found, don't waste time with populating values
            if len(df[df_slice].index):
                # if the hexbin id is present at a larger extent zoom level, inherit it
                df.loc[df_slice, h3_id_col] = df[nxt_h3_col]
                df.loc[df_slice, h3_lvl_col] = nxt_h3_lvl

            # decrement the zoom range
            zoom_range = zoom_range - 1

    return df


def get_h3_hexbins_with_counts(df: pd.DataFrame, h3_id_col: str = 'h3_id',
                               count_column_name: str = None) -> pd.DataFrame:
    """Convert the points with designated Uber H3 ids to hexbins with counts.
    :param df: Pandas DataFrame with H3 ids in a designated column.
    :param h3_id: Column containing the Uber H3 id for each point.
    :param count_column_name: New column name, which will contain the new summarized values.
    :return: Pandas Spatially Enabled Dataframe of hexagon polygons and point counts.
    """
    # provide default
    count_column_name = 'count' if count_column_name is None else count_column_name

    # get the count for each hex id
    h3_id_cnt = df[h3_id_col].value_counts()
    h3_id_cnt.name = count_column_name

    # get the geometries for all the count hex ids
    hex_df = get_h3_hex_dataframe_from_h3_id_lst(h3_id_cnt.index)

    # get the hex levels
    level_df = df[[h3_id_col, h3_lvl_col]].drop_duplicates().set_index(h3_id_col)

    # join the counts to the geometry
    out_df = hex_df.join(h3_id_cnt, on=h3_id_col).join(level_df, on=h3_id_col)

    return out_df


def get_nonoverlapping_h3_hexbins_for_points(spatially_enabled_dataframe: pd.DataFrame, h3_minimum: int = 5,
                                             h3_maximum: int = 9,minimum_threshold_value: int = 100,
                                             weighting_column: str = None) -> pd.DataFrame:
    """Get points summarized by non-overlapping Uber H3 hexbins at mulitiple resolution levels while
    ensuring the minimum count of points is retained in each hexbin. If enough points are not members
    of the lowest level of resolution, this function will continue to aggregate up to the next larger
    hexbin resolution until the largest area (smaller number) is reached. Hexbin areas still without
    enough points to meet the minimum threshold will not be represented.
    :param spatially_enabled_dataframe: Spatially Enabled DataFrame with point geometries to be aggregated.
    :param h3_maximum: Integer maximum H3 grid level defining the samllest geographic hex area - must be larger than the
        minimum.
    :param h3_minimum: Integer minimum H3 grid level defining the largest geograhpic hex area - must be smaller than the
        maximum.
    :param minimum_threshold_value: Minimum count for a grid.
    :param weighting_column: Column from input data to use for point weighting.
    :return: Pandas Spatially Enabled DataFrame
    """
    # add h3 ids
    df = add_h3_ids_to_points(spatially_enabled_dataframe, h3_maximum, h3_minimum)

    # assign h3 grid based on count, and drop those blow the threshold
    cnt_df = get_h3_ids_by_count(df, minimum_threshold_value, count_column=weighting_column)

    # roll up smaller grid id assignments to larger parent hexbins
    cln_cnt_df = remove_overlapping_h3_ids(cnt_df)

    # convert to geometry with count
    out_df = get_h3_hexbins_with_counts(cln_cnt_df, count_column_name=weighting_column)

    return out_df
