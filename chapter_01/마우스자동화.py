import pyautogui
import time

# 1. 화면크기출력
# print(pyautogui.size())

# 2. 마우스위치 출력
time.sleep(2)
print(pyautogui.position())

# 3. 마우스위치 이동
# pyautogui.moveTo(1919,1059)

# 4. 마우스 클릭
# pyautogui.click()
# pyautogui.click(button='right')
# pyautogui.doubleClick()
# pyautogui.click(clicks=3, interval=1) #3번할 건데 1초마다 눌러

# 5. 마우스 드래그
# pyautogui.moveTo(695,72, 2)
# pyautogui.dragTo(498,67, 2)