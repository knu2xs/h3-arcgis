from arcgis.features import GeoAccessor
from h3 import h3
import pandas as pd
import swifter

from . import get_h3_hex_dataframe_from_h3_id_lst

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


def _get_h3_range_lst_from_df(df):
    """Helper to get H3 range list from column names."""
    return [int(col[-2:]) for col in df.columns if col.startswith('h3_') and col[-2:].isnumeric()]


def add_h3_ids_to_points(df: pd.DataFrame, h3_max: int, h3_min: int) -> pd.DataFrame:
    """Add Uber H3 ids to the point geometries in a Saptailly Enabled DataFrame.
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


def get_h3_ids_by_point_count(df: pd.DataFrame, min_count: int) -> pd.DataFrame:
    """Assign a H3 id to each point based on the H3 count in increasingly resolution H3 hexagons. If not enough present, the points
    for the summary tesselation cell will not be retained.
    :param df: Pandas DataFrame with properly formatted columns delineating the Uber H3 ids at varying resolutions.
    :param min_count: The minimum count of points to consider for retaining the H3 id.
    """
    # get the levels from the column names
    h3_lvl_lst = _get_h3_range_lst_from_df(df)

    # ensure the hex levels are sorted in order (larger to smaller area)
    h3_lvl_lst.sort()

    # iterate the hex levels
    for h3_lvl in h3_lvl_lst:
        # create the hex column name string
        h3_col = _h3_col(h3_lvl)

        # get the count of every hex id at this resolution
        h3_id_cnt = df[h3_col].value_counts()

        # if the count for the hex id is greater than the minimum, assign an id - critical for PII
        h3_id_lst = h3_id_cnt[h3_id_cnt > min_count].index.values

        # create a slice expression for just records matching the saved hex ids
        df_slice = df[h3_col].isin(h3_id_lst)

        # save the hex id's in the final column for the values exceeding the threshold
        df.loc[df_slice, h3_id_col] = df[df_slice][h3_col]
        df.loc[df_slice, h3_lvl_col] = h3_lvl

        # Note the hex level
        df.loc[df_slice, h3_lvl_orig_col] = h3_lvl

    # drop values not meeting the threshold - this is the key step for protecting PII
    df.dropna(subset=[h3_id_col, h3_lvl_col], inplace=True)

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
        # get the name of the column at the next zoom level
        nxt_h3_lvl = h3_lvl - 1
        nxt_h3_col = _h3_col(nxt_h3_lvl)

        # create a filter to identify only the records where the next zoom level, the containing h3,
        # is also being used
        df_slice = df[nxt_h3_col].isin(h3_id_lst)

        # if the hexbin id is present at a larger extent zoom level, inherit it
        df.loc[df_slice, h3_id_col] = df[nxt_h3_col]
        df.loc[df_slice, h3_lvl_col] = nxt_h3_lvl

    return df


def get_h3_hexbins_with_counts(df: pd.DataFrame, h3_id_col: str = 'h3_id') -> pd.DataFrame:
    """Convert the points with designated Uber H3 ids to hexbins with counts.
    :param df: Pandas DataFrame with H3 ids in a designated column.
    :param h3_id: Column containing the Uber H3 id for each point.
    :return: Pandas Spatially Enabled Dataframe of hexagon polygons and point counts.
    """
    # get the count for each hex id
    h3_id_cnt = df[h3_id_col].value_counts()
    h3_id_cnt.name = 'count'

    # get the geometries for all the count hex ids
    hex_df = get_h3_hex_dataframe_from_h3_id_lst(h3_id_cnt.index)

    # get the hex levels
    level_df = df[[h3_id_col, h3_lvl_col]].drop_duplicates().set_index(h3_id_col)

    # join the counts to the geometry
    out_df = hex_df.join(h3_id_cnt, on=h3_id_col).join(level_df, on=h3_id_col)

    return out_df


def get_nonoverlapping_h3_hexbins_for_points(sdf: pd.DataFrame, h3_min: int = 5, h3_max: int = 9,
                                             min_count: int = 100) -> pd.DataFrame:
    """Get points summarized by non-overlapping Uber H3 hexbins at mulitiple resolution levels while
    ensuring the minimum count of points is retained in each hexbin. If enough points are not members
    of the lowest level of resolution, this function will continue to aggregate up to the next larger
    hexbin resolution until the largest area (smaller number) is reached. Hexbin areas still without
    enough points to meet the minimum threshold will not be represented.
    :param df: Spatially Enabled DataFrame with point geometries to be aggregated.
    :param h3_max: Integer maximum H3 grid level defining the samllest geographic hex area - must be larger than the minimum.
    :param h3_min: Integer minimum H3 grid level defining the largest geograhpic hex area - must be smaller than the maximum.
    :param min_count: Minimum point count for a grid.
    """
    # add h3 ids
    df = add_h3_ids_to_points(sdf, h3_max, h3_min)

    # assign h3 grid based on count, and drop those blow the threshold
    cnt_df = get_h3_ids_by_point_count(df, min_count)

    # roll up smaller grid id assignments to larger parent hexbins
    cln_cnt_df = remove_overlapping_h3_ids(cnt_df)

    # convert to geometry with count
    out_df = get_h3_hexbins_with_counts(cln_cnt_df)

    return out_df
