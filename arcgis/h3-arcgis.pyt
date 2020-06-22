# -*- coding: utf-8 -*-
import sys

from arcgis.features import GeoAccessor
import arcpy

# import the h3 arcgis library
sys.path.insert(0, '../src')
import h3_arcgis


class Toolbox(object):
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the
        .pyt file)."""
        self.label = "H3-ArcGIS"
        self.alias = "h3_arcgis"

        # List of tool classes associated with this toolbox
        self.tools = [CreateH3Tessellation]


class CreateH3Tessellation(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Create H3 Tessellation"
        self.description = "Create H3 hexagon tessellation at a specific scale."
        self.canRunInBackground = False

    def getParameterInfo(self):
        """Define parameter definitions"""
        param0 = arcpy.Parameter(
            displayName="Area of Interest",
            name="aoi",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param0.filter.list = ["Polygon"]

        param1 = arcpy.Parameter(
            displayName="Uber H3 Level",
            name="h3_lvl",
            datatype="GPLong",
            parameterType="Required",
            direction="Input")
        param1.value = 6
        param1.filter.type = "ValueList"
        param1.filter.list = list(range(1, 16))

        param3 = arcpy.Parameter(
            displayName="Output H3 Tessellation Feature Class",
            name="out_h3_fc",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output")

        params = [param0, param1, param3]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        in_aoi = parameters[0].valueAsText
        h3_lvl = parameters[1].value
        out_fc = parameters[2].valueAsText

        # Ensure single part geometry by dissolving into single feature with single geometry since H3 cannot handle
        # multipart geometries. Consolidating into single feature is additional beneficial byproduct.
        in_aoi = arcpy.management.Dissolve(
            in_features=in_aoi,
            out_feature_class='memory/h3_aoi',
            multi_part=False
        )[0]

        in_df = GeoAccessor.from_featureclass(in_aoi)
        out_df =h3_arcgis.get_h3_hex_for_aoi(orig_df=in_df, hex_level=h3_lvl)
        out_fc_pth = out_df.spatial.to_featureclass(out_fc)
        return out_fc_pth
