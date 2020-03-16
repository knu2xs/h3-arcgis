import arcpy
import arcgis
import json
import os
import tempfile
import traceback
import shutil
from arcgis.gis import GIS
from arcgis.features import GeoAccessor
from arcgis.features import FeatureSet
from functools import wraps
from h3 import h3
import pandas as pd
from geojson.feature import *


def Create_FL(LayerName, FCPath, expression=''):
    '''
    Create a Feature layer from a feature class. Optionally, an expression clause can be passed 
    in to filter out a subset of data.
    '''
    if arcpy.Exists(LayerName):
        desc = arcpy.Describe(LayerName)
        if desc.dataType is "FeatureLayer":
            arcpy.Delete_management(LayerName)
    try:
        if expression:
            return arcpy.MakeFeatureLayer_management(FCPath, LayerName, expression, "")
        else:
            return arcpy.MakeFeatureLayer_management(FCPath, LayerName, "", "")
    except:
        return arcpy.AddError(arcpy.GetMessages(2))


def InputCheck(Input_Layer):
    '''
    Check if there is a filepath from the input layers. If not, pre-pend the path. 
    Also extract the FC names.
    '''
    if arcpy.Exists(Input_Layer):
        # join(arcpy.Describe(Input_Layer).catalogPath,arcpy.Describe(Input_Layer).name)
        InputPath = arcpy.Describe(Input_Layer).catalogPath
        InputName = arcpy.Describe(Input_Layer).name
    else:
        arcpy.AddError("{} Does not exist".format(Input_Layer))
        sys.exit()
    return InputPath, InputName


def get_bounding_box_extent(input_layer_path):
    """ Return the bounding box extent in a geojson format
    """

    desc_lyr = arcpy.Describe(input_layer_path)
    x_max = desc_lyr.extent.XMax
    x_min = desc_lyr.extent.XMin
    y_max = desc_lyr.extent.YMax
    y_min = desc_lyr.extent.YMin
    Input_Extent = {"type":"Polygon","coordinates":[[[x_min, y_min],
                                                [x_max, y_min],
                                                [x_max, y_max],
                                                [x_min, y_max],
                                                [x_min, y_min]]]}
    return Input_Extent


def h3code_to_geom(df):
    
    '''Use h3.geo_to_h3 to index each data point into the spatial index of the specified resolution.
    Use h3.h3_to_geo_boundary to obtain the geometries of these hexagons
    '''
    df["geometry"] =  df.hex_id.apply(lambda x: 
                                      {"type" : "Polygon",
                                       "coordinates": 
                                       [h3.h3_to_geo_boundary(h3_address=x,geo_json=True)],
                                       'spatial eference': {'wkid': 4326}
                                       })
    
    return df


def hexagons_dataframe_to_geojson(df_hex, file_output = None):
    
    '''Produce the GeoJSON for a dataframe that has a geometry column in geojson 
    format already, along with the columns hex_id and value
    '''
    
    list_features = []
    
    for i,row in df_hex.iterrows():
        feature = Feature(geometry = row["geometry"] , properties={'hex_id': row["hex_id"]})
        list_features.append(feature)
        
    feat_collection = FeatureCollection(list_features)
    
    geojson_result = json.dumps(feat_collection)

    #optionally write to file
    if file_output is not None:
        with open(file_output,"w") as f:
            json.dump(feat_collection,f)
    
    return geojson_result


def temp_handler(func):
    """
    Wrapper function that appends a temporary file directory value that's passed into
    the build_fc function. The directory path is used to temporarily store the .csv
    downloaded for processing. After processing has finished, file contents and directory
    are removed.
    """

    @wraps(func)
    def wrap(*args, **kwargs):

        temp_dir = tempfile.mkdtemp()

        args = list(args)
        args.insert(1, temp_dir)

        try:
            func(*args, **kwargs)
        except:
            arcpy.AddMessage(traceback.format_exc())
        finally:
            shutil.rmtree(temp_dir)
            arcpy.AddMessage(f'Removed Temp Directory: {temp_dir}')

    return wrap


@temp_handler
def build_grids(resolution, tempdir, extent, output_path):
    # Pass in our extent and resolution parameters and return a set of of hexagons that fill
    # extent as a list.

    hexagons = list(h3.polyfill(extent, resolution, geo_json_conformant=True))
    # Convert the list of hexagons into a dataframe and index each grid with the corresponding the hex_id
    df_raw = h3code_to_geom(pd.DataFrame(hexagons, columns=['hex_id']))

    # Export our dataframe to a geojson
    file_name = f'h3_hex{resolution}'
    geojson_output_path = os.path.join(tempdir, f'{file_name}.geojson')
    raw_geojson = hexagons_dataframe_to_geojson(df_raw, geojson_output_path)
    
    with open(geojson_output_path) as data:
        geojson = json.load(data)

    fromJSON = arcgis.features.FeatureSet.from_geojson(geojson)
    sdf = fromJSON.sdf
    full_hfl = sdf.spatial.to_featureclass(output_path, overwrite=True)


class Toolbox(object):
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the
        .pyt file)."""
        self.label = "Toolbox"
        self.alias = ""

        # List of tool classes associated with this toolbox
        self.tools = [CreateGrids]


class CreateGrids(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Polygon to H3 Grids"
        self.description = "Tool to create grids that that are within a user supplied polygon or a user drawn polygon"
        self.canRunInBackground = False

    def getParameterInfo(self):
        """Define parameter definitions"""

        param0 = arcpy.Parameter(
            displayName='Enter a resolution value between 0 and 15',
            name="ResolutionValue",
            datatype='GPString',
            parameterType="Required",
            direction="Input",
            multiValue=False
        )

        param1 = arcpy.Parameter(
            displayName='Layer Name',
            name="layer_name",
            datatype='DEFeatureClass',
            parameterType="Required",
            direction="Output",
            multiValue=False
        )

        param2 = arcpy.Parameter(
            displayName='Draw an area of interst',
            name="UserDrawn",
            datatype='GPFeatureRecordSetLayer',
            parameterType="Optional",
            direction="Input",
            multiValue=False
        )

        param3 = arcpy.Parameter(
            displayName='Only return grids within bounding box of layer',
            name="ExtentOnly",
            datatype='GPBoolean',
            parameterType="Optional",
            direction="Input",
            multiValue=False
        )
        
        # Setting default value for FlattenFlag/ArticleFlag boolean
        param3.value = False

        params = [param0, param1, param2, param3]

        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""

        if parameters[0].altered:
            parameters[1].value = f'h3_hex{parameters[0].valueAsText}'
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        return

    def execute(self, parameters, messages):
        """The source code of the tool."""

        fc_path, fc_name = InputCheck(parameters[2].valueAsText)

        # Get bounding box from extent layer.
        extent = get_bounding_box_extent(fc_path)

        build_grids(
            int(parameters[0].value),
            extent,
            parameters[1].valueAsText)
        
        if bool(parameters[3].value) is False:
            # In order to delete selected features from a layer, we must create a feature layer.
            Create_FL('tmp', parameters[1].valueAsText)

            # Select all grids that are outside of the input polygon and delete
            arcpy.management.SelectLayerByLocation('tmp', "HAVE_THEIR_CENTER_IN", fc_path, None, "NEW_SELECTION", "INVERT")
            arcpy.AddMessage('Removing {} features'.format(arcpy.GetCount_management('tmp')[0]))
            arcpy.DeleteFeatures_management('tmp')
            

        return
