import pyautogui
import time
 
pyautogui.write('hello world!') # 괄호 안의 문자를 타이핑 합니다.
pyautogui.write('hello world!', interval=0.25) # 각 문자를 0.25마다 타이핑합니다. 



import pyperclip

pyperclip.copy("안녕하세요") # 클립보드에 텍스트를 복사합니다. 

pyautogui.hotkey('ctrl', 'v') # 붙여넣기 (hotkey 설명은 아래에 있습니다.)


pyautogui.press('shift') # shift 키를 누릅니다.
pyautogui.press('ctrl') # ctrl 키를 누릅니다. 


pyautogui.keyDown('ctrl') # ctrl 키를 누른 상태를 유지합니다.
pyautogui.press('c') # c key를 입력합니다. 
pyautogui.keyUp('ctrl') # ctrl 키를 뗍니다. 


pyautogui.press(['left', 'left', 'left']) # 왼쪽 방향키를 세번 입력합니다.
pyautogui.press('left', presses=3) # 왼쪽 방향키를 세번 입력합니다. 
pyautogui.press('enter', presses=3, interval=3) # enter 키를 3초에 한번씩 세번 입력합니다. 


pyautogui.hotkey('ctrl', 'c') # ctrl + c 키를 입력합니다. 


['\t', '\n', '\r', ' ', '!', '"', '#', '$', '%', '&', "'", '(',
')', '*', '+', ',', '-', '.', '/', '0', '1', '2', '3', '4', '5', '6', '7',
'8', '9', ':', ';', '<', '=', '>', '?', '@', '[', '\\', ']', '^', '_', '`',
'a', 'b', 'c', 'd', 'e','f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o',
'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z', '{', '|', '}', '~',
'accept', 'add', 'alt', 'altleft', 'altright', 'apps', 'backspace',
'browserback', 'browserfavorites', 'browserforward', 'browserhome',
'browserrefresh', 'browsersearch', 'browserstop', 'capslock', 'clear',
'convert', 'ctrl', 'ctrlleft', 'ctrlright', 'decimal', 'del', 'delete',
'divide', 'down', 'end', 'enter', 'esc', 'escape', 'execute', 'f1', 'f10',
'f11', 'f12', 'f13', 'f14', 'f15', 'f16', 'f17', 'f18', 'f19', 'f2', 'f20',
'f21', 'f22', 'f23', 'f24', 'f3', 'f4', 'f5', 'f6', 'f7', 'f8', 'f9',
'final', 'fn', 'hanguel', 'hangul', 'hanja', 'help', 'home', 'insert', 'junja',
'kana', 'kanji', 'launchapp1', 'launchapp2', 'launchmail',
'launchmediaselect', 'left', 'modechange', 'multiply', 'nexttrack',
'nonconvert', 'num0', 'num1', 'num2', 'num3', 'num4', 'num5', 'num6',
'num7', 'num8', 'num9', 'numlock', 'pagedown', 'pageup', 'pause', 'pgdn',
'pgup', 'playpause', 'prevtrack', 'print', 'printscreen', 'prntscrn',
'prtsc', 'prtscr', 'return', 'right', 'scrolllock', 'select', 'separator',
'shift', 'shiftleft', 'shiftright', 'sleep', 'space', 'stop', 'subtract', 'tab',
'up', 'volumedown', 'volumemute', 'volumeup', 'win', 'winleft', 'winright', 'yen',
'command', 'option', 'optionleft', 'optionright']
