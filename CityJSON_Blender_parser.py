bl_info = {
    "name": "Import CityJSON files",
    "author": "Konstantinos Mastorakis",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "File > Import > CityJSON (.json)",
    "description": "Visualize 3D City Models encoded in CityJSON format",
    "warning": "",
    "wiki_url": "",
    "category": "Import-Export",
}
import time
import bpy
import json
import random
from bpy_extras.io_utils import ImportHelper, ExportHelper
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.types import Operator



def clean_list(values):
    #Creates a list of non list in case lists nested in lists exist
    while isinstance(values[0],list):
        values = values[0]
    return values

def assign_properties(obj, props, prefix=[]):
    #Assigns the custom properties to obj based on the props
    for prop, value in props.items():
        
        if prop in ["geometry", "children", "parents"]:
            continue

        if isinstance(value, dict):
            obj = assign_properties(obj, value, prefix + [prop])
        
        else:
            obj[".".join(prefix + [prop])] = value

    return obj

def coord_translate_axis_origin(vertices):
    #Translating function to origin
    #Finding minimum value of x,y,z
    minx = min(i[0] for i in vertices)
    miny = min(i[1] for i in vertices)
    minz = min(i[2] for i in vertices)
    
    #Calculating new coordinates
    translated_x = [i[0]-minx for i in vertices]
    translated_y = [i[1]-miny for i in vertices]
    translated_z = [i[2]-minz for i in vertices]
    
    return (tuple(zip(translated_x,translated_y,translated_z)),minx,miny,minz)


def original_coordinates(vertices,minx,miny,minz):
    #Translating back to original coords 
    #Calculating original coordinates
    original_x = [i[0]+minx for i in vertices]
    original_y = [i[1]+miny for i in vertices]
    original_z = [i[2]+minz for i in vertices]
    
    return (tuple(zip(original_x,original_y,original_z)))

def clean_buffer(vertices, bounds):
    #Cleans the vertices index from unused vertices3
    new_bounds = list()
    new_vertices = list()
    i=0
    for bound in bounds:
        new_bound = list()
        
        for j in range(len(bound)):
            new_vertices.append(vertices[bound[j]])
            new_bound.append(i)
            i=i+1
        
        new_bounds.append(tuple(new_bound))
    
    return new_vertices, new_bounds

def write_cityjson(context, filepath):
    #Will write all scene data in CityJSON format"
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump("No problem", f, ensure_ascii=False, indent=4)
    
    return {'FINISHED'}

def geometry_renderer(data,vertices,theid,index):
    #Parsing the boundary data of every geometry
    bound=list()                
    
    geom = data['CityObjects'][theid]['geometry'][index]
    if 'lod' in geom:
        prefix = "LOD_" + str(geom['lod'])
    else:
        prefix = "no_LOD_"+str(index)
    
    #Checking how nested the geometry is i.e what kind of 3D geometry it contains
    if((geom['type']=='MultiSurface') or (geom['type'] == 'CompositeSurface')):
    
        for face in geom['boundaries']:
            # This if - else statement ignores all the holes if any in any geometry
            if len(face)>0:
                bound.append(tuple(face[0]))
        
    elif (geom['type']=='Solid'):
        for shell in geom['boundaries']:
            for face in shell:
                if (len(face)>0):
                    bound.append(tuple(face[0]))
                                                    
    elif (geom['type']=='MultiSolid'):
        for solid in geom['boundaries']:
            for shell in solid:
                for face in shell:
                    if (len(face)>0):
                        bound.append(tuple(face[0]))
    
    temp_vertices, temp_bound = clean_buffer(vertices, bound)
    
    #Visualization part
    geometryname = prefix+"_"+ theid
    mesh_data = bpy.data.meshes.new("mesh")
    mesh_data.from_pydata(temp_vertices, [], temp_bound)
    mesh_data.update()    
    geom_obj = bpy.data.objects.new(geometryname, mesh_data)
    scene = bpy.context.scene
    scene.collection.objects.link(geom_obj)
    
    #Assigning attributes to geometries
    geom_obj = assign_properties(geom_obj, data["CityObjects"][theid])

    #Assigning semantics to every face of every geometry         
    if 'semantics' in geom:
        values = geom['semantics']['values']
        
        for surface in geom['semantics']['surfaces']:
            mat = bpy.data.materials.new(name="Material")
            assign_properties(mat, surface)                   
            #Assigning materials on each object
            geom_obj.data.materials.append(mat)
            
            #Assign color based on surface type            
            if surface['type'] =='WallSurface':
                mat.diffuse_color = (0.8,0.8,0.8,1)                            
            elif surface['type'] =='RoofSurface':
                mat.diffuse_color = (0.9,0.057,0.086,1)                                       
            elif surface['type'] =='GroundSurface':
                mat.diffuse_color = (0.507,0.233,0.036,1)                            
            else:
                mat.diffuse_color = (0,0,0,1)
        geom_obj.data.update()                       
        values = clean_list(values)
        
        i=0        
        for face in geom_obj.data.polygons:
            face.material_index = values[i]
            i+=1

    return geom_obj

def cityjson_parser(context, filepath):
    print("Importing CityJSON file...")
    #Deleting previous objects every time a new CityJSON file is imported
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=True)
            
    #Read CityJSON file
    with open(filepath) as json_file:
        data = json.load(json_file)
        vertices=list() 
           
        #Checking if coordinates need to be transformed and transforming if necessary 
        if 'transform' not in data:
            for vertex in data['vertices']:
                vertices.append(tuple(vertex))
        else:
            trans_param = data['transform']
            #Transforming coords to actual real world coords
            for vertex in data['vertices']:
                x=vertex[0]*trans_param['scale'][0]+trans_param['translate'][0]
                y=vertex[1]*trans_param['scale'][1]+trans_param['translate'][1]
                z=vertex[2]*trans_param['scale'][2]+trans_param['translate'][2]
                vertices.append((x,y,z))
        
        #Translating coordinates to the axis origin
        translation = coord_translate_axis_origin(vertices)
        
        #Updating vertices with new translated vertices
        vertices = translation[0]
                
        progress_max = len(data['CityObjects'])        
        progress = 0
        start_render = time.time()
        #Creating empty meshes for every CityObjects and linking its geometries as children-meshes
        for theid in data['CityObjects']:
            cityobject = bpy.data.objects.new(theid, None)
            cityobject = assign_properties(cityobject, data["CityObjects"][theid])
            scene = bpy.context.scene
            scene.collection.objects.link(cityobject)
                        
            for i in range(len(data['CityObjects'][theid]['geometry'])):
                geom_obj = geometry_renderer(data,vertices,theid,i)
                geom_obj.parent = cityobject
            progress+=1
            
            print ("Rendering: " + str(round(progress*100/progress_max, 1))+"% completed", end="\r")    
        end_render = time.time()
                
        progress = 0
        start_hier = time.time()
        #Assigning child building parts to parent buildings   
        for theid in data['CityObjects']:
            if 'parents' in data['CityObjects'][theid]:
                bpy.data.objects[theid].parent = bpy.data.objects[data['CityObjects'][theid]['parents'][0]]
            progress+=1
            print ("Building Hierarchy " + str(round(progress*100/progress_max, 1))+"% completed",end="\r")
        end_hier= time.time()
        
        #Console output
        print ("\n")
        print("CityJSON file successfully imported!\n")
        print ("Total Rendering Time: ", round(end_render-start_render,2),"s")
        print ("Building Hierarchy: ", round(end_hier-start_hier,2),"s")
        
    return {'FINISHED'}

class ImportCityJSON(Operator, ImportHelper):
    "Load a CityJSON file"
    bl_idname = "import_test.some_data"  # important since its how bpy.ops.import_test.some_data is constructed
    bl_label = "Import CityJSON"

    # ImportHelper mixin class uses this
    filename_ext = ".json"

    filter_glob: StringProperty(
        default="*.json",
        options={'HIDDEN'},
        maxlen=255,  # Max internal buffer length, longer would be clamped.
    )
    def execute(self, context):
        return cityjson_parser(context, self.filepath) #self.use_setting)

class ExportCityJSON(Operator, ExportHelper):
    "Export scene as a CityJSON file"
    bl_idname = "export_test.some_data"  # important since its how bpy.ops.import_test.some_data is constructed
    bl_label = "Export CityJSON"

    # ExportHelper mixin class uses this
    filename_ext = ".json"

    filter_glob: StringProperty(
        default="*.json",
        options={'HIDDEN'},
        maxlen=255,  # Max internal buffer length, longer would be clamped.
    )
    def execute(self, context):
        return write_cityjson(context, self.filepath)

# Only needed if you want to add into a dynamic menu
def menu_func_export(self, context):
    self.layout.operator(ExportCityJSON.bl_idname, text="CityJSON (.json)")

# Only needed if you want to add into a dynamic menu
def menu_func_import(self, context):
    self.layout.operator(ImportCityJSON.bl_idname, text="CityJSON (.json)")
    
def register():
    bpy.utils.register_class(ImportCityJSON)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    
    bpy.utils.register_class(ExportCityJSON)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

def unregister():
    bpy.utils.unregister_class(ImportCityJSON)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    
    bpy.utils.unregister_class(ExportCityJSON)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)

if __name__ == "__main__":
    register()
    bpy.ops.import_test.some_data('INVOKE_DEFAULT')
