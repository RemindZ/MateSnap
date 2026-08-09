import importlib
import logging
import sys
from . import addon_updater_ops

bl_info = {
    "name": "MateSnap",
    "author": "RemindZ, based on QuickSnap by Julien Heijmans",
    "blender": (2, 93, 0),
    'version': (2, 0, 1),
    "category": "3D View",
    "description": "Mate kit and figurine parts with precision snapping",
    "warning": "",
    "doc_url": "https://github.com/RemindZ/MateSnap",
    "releases_url": "https://github.com/RemindZ/MateSnap/releases",
    "tracker_url": "https://github.com/RemindZ/MateSnap/issues",
}


modulesNames = ['addon_updater', 'addon_updater_ops', 'quicksnap_utils', 'quicksnap_snapdata', 'quicksnap_render',
                'quicksnap']

modulesFullNames = {}
for currentModuleName in modulesNames:
    modulesFullNames[currentModuleName] = ('{}.{}'.format(__name__, currentModuleName))

for currentModuleFullName in modulesFullNames.values():
    if currentModuleFullName in sys.modules:
        importlib.reload(sys.modules[currentModuleFullName])
    else:
        globals()[currentModuleFullName] = importlib.import_module(currentModuleFullName)
        setattr(globals()[currentModuleFullName], 'modulesNames', modulesFullNames)


def register():
    for current_module_name in modulesFullNames.values():
        if current_module_name in sys.modules:
            if hasattr(sys.modules[current_module_name], 'register'):
                if current_module_name == f"{__name__}.addon_updater_ops":
                    sys.modules[current_module_name].register(bl_info)
                else:
                    sys.modules[current_module_name].register()


def unregister():
    # Purge any draw handlers left registered (e.g. if a tool session was running), so they do not
    # keep firing against a freed operator after the addon is disabled or reloaded.
    render_module = sys.modules.get(f"{__name__}.quicksnap_render")
    if render_module is not None and hasattr(render_module, 'remove_draw_handlers'):
        try:
            render_module.remove_draw_handlers()
        except Exception:
            pass
    for current_module_name in modulesFullNames.values():
        if current_module_name in sys.modules:
            if hasattr(sys.modules[current_module_name], 'unregister'):
                sys.modules[current_module_name].unregister()


logger = logging.getLogger(__name__)
logger.handlers = []
logger.setLevel(logging.NOTSET)
console_handler = logging.StreamHandler()
console_handler.setFormatter(fmt=logging.Formatter('[%(levelname)s] %(asctime)s %(message)s'))
logger.addHandler(console_handler)
