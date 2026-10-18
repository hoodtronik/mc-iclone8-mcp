import RLPy


_SEARCH_TYPES = (
    RLPy.EObjectType_Prop,
    RLPy.EObjectType_Avatar,
    RLPy.EObjectType_Camera,
    RLPy.EObjectType_Particle,
    RLPy.EObjectType_Light,
    RLPy.EObjectType_SpotLight,
    RLPy.EObjectType_PointLight,
    RLPy.EObjectType_DirectionalLight,
)

if hasattr(RLPy, "EObjectType_Path"):
    _SEARCH_TYPES += (RLPy.EObjectType_Path,)


def find_by_name(name):
    # The active Preview Camera is not always returned by FindObject, even
    # though it is a valid camera with a transform control.
    current_camera = RLPy.RScene.GetCurrentCamera()
    if current_camera is not None and current_camera.GetName() == name:
        return current_camera
    for object_type in _SEARCH_TYPES:
        obj = RLPy.RScene.FindObject(object_type, name)
        if obj is not None:
            return obj
    # CLAUDE-NOTE (2026-10-18, measured): Crowd Generator actors are RILightAvatar (type 16384); FindObject /
    # FindObjects return NONE of them for any type (Avatar, LightAvatar, Object), only RScene.GetAvatars() lists them.
    for av in RLPy.RScene.GetAvatars():
        if av.GetName() == name:
            return av
    raise ValueError("Object not found: %s" % name)
