from phue import Bridge
from typing import Union, Tuple, Dict
import re
import vim
import time
import os


def _variable_exists(name: str) -> bool:
    """
    Check if the specified variable exists

    :param name str: Name of the variable e.g. `g:testVariable`
    :rtype bool: Whether the variable exists
    """
    return int(vim.eval(f'exists("{name}")')) == 1


def _get_global_variable(name: str, default=None) -> Union[None, any]:
    """
    Get a global variable or a default value if it does not exist (if not set
    this is None)

    :param name str: Name of the variable. Can but does not have to start
    with `g:`
    :param default any: Default value to return if the variable does not exist
    """
    _default = f'"{default}"' if type(default) is str else default
    if default is not None:
        return vim.eval(f"get(g:, '{name.lstrip('g:')}', {_default})")
    else:
        if not name.startswith("g:"):
            name = "g:" + name
        if _variable_exists(name):
            return vim.eval(name)
        else:
            return None


def _get_config(isStartup: bool = False) -> Union[None, Dict[str, any]]:
    """
    Get the hardware configuration- bridge ip and light name as a tuple-
    if the necessary variables are configured otherwise print an error

    :param isStartup bool: Skip/return None if true and disable on
    startup is true
    """
    if not (isStartup and _get_global_variable("g:hiHue#disableAtStart", 0) == 1):
        if not _variable_exists('g:hiHue#bridge_ip'):
            print("Bridge ip not defined. Please define it with e.g. `let g:hiHue#bridge_ip = '192.168.1.123'` or disable hiHue on startup")
            return None
        if not _variable_exists('g:hiHue#light_name'):
            print("Light name not defined. Please define it with e.g. `let g:hiHue#light_name = 'My light'` or disable hiHue on startup")
            return None
        return {
            'light': vim.eval('g:hiHue#light_name'),
            'ip': vim.eval('g:hiHue#bridge_ip')
        }
    else:
        return None


def _phue_config_path():
    """
    Get the path to the configuration file. If g:hiHue#phueConfigPath is set
    return its value, otherwise return `#/.phue` where # is the root of this
    plugin
    """
    if _variable_exists("g:hiHue#phueConfigPath"):
        return _get_global_variable("g:hiHue#phueConfigPath")
    else:
        p = os.path.dirname(vim.eval('resolve(expand("<sfile>:p"))'))
        p = os.path.abspath(os.path.join(p, '../', '.phue'))
        vim.command(f"let g:hiHue#phueConfigPath = '{p}'")
        return p


def _connect(isStartup=False) -> Tuple[Union[Bridge, None], Union[Dict[str, any], None]]:
    config = _get_config(isStartup)
    if config is None:
        return None, None
    newlyRegistered = not os.path.isfile(_phue_config_path())
    b = Bridge(config['ip'], config_file_path=_phue_config_path())
    b.connect()
    if newlyRegistered:
        print("Successfully registered bridge at {config['ip']}")
    return b, config


def _disconnect():
    global bridge
    bridge = None


def _deregister() -> bool:
    _disconnect()
    p = _phue_config_path()
    if os.path.isfile(p):
        os.remove(p)
        return True
    else:
        return False


# Init configuration
if os.path.isfile(_phue_config_path()):
    bridge, config = _connect(isStartup=True)
else:
    bridge, config = None, None


def _rgb_to_xy(red, green, blue):
    """
    Conversion of RGB colors to CIE1931 XY colors
    Formulas implemented from: https://gist.github.com/popcorn245/30afa0f98eea1c2fd34d
    Args:
        red (float): a number between 0.0 and 1.0 representing red in the RGB space
        green (float): a number between 0.0 and 1.0 representing green in the RGB space
        blue (float): a number between 0.0 and 1.0 representing blue in the RGB space
    Returns:
        xy (list): x and y
    """

    # gamma correction
    red = pow((red + 0.055) / (1.0 + 0.055),
              2.4) if red > 0.04045 else (red / 12.92)
    green = pow((green + 0.055) / (1.0 + 0.055),
                2.4) if green > 0.04045 else (green / 12.92)
    blue = pow((blue + 0.055) / (1.0 + 0.055),
               2.4) if blue > 0.04045 else (blue / 12.92)

    # convert rgb to xyz
    x = red * 0.649926 + green * 0.103455 + blue * 0.197109
    y = red * 0.234327 + green * 0.743075 + blue * 0.022598
    z = green * 0.053077 + blue * 1.035763

    # convert xyz to xy
    x = x / (x + y + z)
    y = y / (x + y + z)

    return [x, y]


lastWord = ""
lastTimestamp = 0
currentColor = None
lightIsFallback = True
fallbackIfNotOverColor = int(_get_global_variable(
    "g:hiHue#fallbackIfNotOverColor", default=1)) == 1
colorPattern = re.compile("#[a-fA-F0-9]{3}([a-fA-F0-9]{3})?")


def _set_color(color, force=False):
    global currentColor
    if bridge is None or config is None:
        print("No bridge or config")
        return
    if type(color) is str:
        color = tuple(
            int(color.lstrip('#')[i:i+2], 16) / 255 for i in (0, 2, 4))
    # Assume color is a tuple or list of 3 components
    if currentColor != color or force:
        try:
            if color != (0, 0, 0):
                bridge.set_light(config['light'], 'on', True)
                bridge.set_light(config['light'],
                                 'bri',
                                 int(float(_get_global_variable(
                                     "g:hiHue#maxBrightness", 1.0)) * 255)
                                 )
                light = bridge.get_light_objects('name')[config['light']]

                light.xy = _rgb_to_xy(color[0], color[1], color[2])
                currentColor = color
            else:
                bridge.set_light(config['light'], 'on', False)
                currentColor = (0, 0, 0)
        except Exception as e:
            print(f"[HiHue] Error: {e}")
    return color


# Set the light to black aka off
fallbackColor = _set_color(_get_global_variable(
    "g:hiHue#fallbackColor", "00000"))


def try_highlight_word():
    word = vim.eval("expand('<cWORD>')")
    global lastWord
    global lastTimestamp
    if lastWord != word and time.time_ns() // 10E3 - lastTimestamp >= 1000:
        if colorPattern.match(word):
            _set_color(word)
            lastWord = word
            lightIsFallback = False
        elif fallbackIfNotOverColor:
            _set_color(fallbackColor)
            lastWord = None
            lightIsFallback = True
        lastTimestamp = time.time_ns() // 10E6


def status():
    """
    Print status information
    """
    if not os.path.isfile(_phue_config_path()):
        print("No registered bridge!\nRegister with :HiHueConnect. Note: Run this command within 30 seconds after pressing the button on the bridge\n")
    print(f"Connected = {bridge is not None}")
    print(f"IP = {config.get('ip', None) if config is not None else None}")
    print(
        f"Light name = {config.get('light', None) if config is not None else None}")

    print(
        f"phue Path = {_phue_config_path()}{'' if os.path.isfile(_phue_config_path()) else '*' }")
    print(f"Color = {currentColor}")
    print(f"On fallback = {lightIsFallback}")


def connect(*vargs):
    if len(vargs) > 2:
        print("Too many arguments")
        return

    if len(vargs) == 1:
        # Infer whether the provided arguments is the IP or light name based on
        # a regex. This means that addresses resolved by a DNS cannot be
        # provided this way

        # Source: https://www.oreilly.com/library/view/regular-expressions-cookbook/9780596802837/ch07s16.html
        # and https://www.oreilly.com/library/view/regular-expressions-cookbook/9780596802837/ch07s17.html
        if re.match(r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$", arg) or re.match(r"\A(?:[A-F0-9]{1,4}:){7}[A-F0-9]{1,4}\Z", arg):
            ip = vargs[0]
        else:
            lightName = vargs[0]
    elif len(vargs) == 2:
        ip = vargs[0]
        lightName = vargs[1]
    else:
        ip, lightName = None, None

    if ip is not None:
        vim.command('let g:hiHue#bridge_ip =' + ip)
    if lightName is not None:
        vim.command('let g:hiHue#light_name =' + lightName)

    global bridge, config
    bridge, config = _connect(isStartup=False)


def disconnect():
    _disconnect()


def deregister():
    if _deregister():
        print("Deregistered bridge")
    else:
        print("Nothing to deregister")
