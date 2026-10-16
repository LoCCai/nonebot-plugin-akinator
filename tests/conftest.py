"""Import framework-free modules without starting NoneBot or contacting a server."""
from pathlib import Path
import sys
import types

package = types.ModuleType("akinator_core_test")
package.__path__ = [str(Path(__file__).resolve().parents[1] / "nonebot_plugin_akinator")]
sys.modules[package.__name__] = package
