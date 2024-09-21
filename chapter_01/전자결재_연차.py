import pyautogui
import time

# PositionInfo
#     전자결재 73,322
#     결재대기문서 215,299
#     결재문서제목 776,277
#     기안자뒤 514,321
#     기안자앞 462,319
#     근무일시앞 480,505
#     근무일시뒤 543,505
#     근무시작시간앞 482,519
#     근무시작시간뒤 505,520
#     근무종료시간앞 512,520
#     근무종료시간뒤 535,519
#     총근무시간앞 622,499
#     총근무시간뒤 651,498
#     근무내용앞 712,491 
#     근무내용뒤 1025,533
#     엣지위치 778,1057


#베러웨이그룹웨어 메신져 켜서 전자결재까지 들어가기
pyautogui.moveTo(498,1051)
pyautogui.click(button='left', interval=0.25)
pyautogui.write('Bett')
pyautogui.moveTo(551,429)
pyautogui.click(button='left')
time.sleep(1)
pyautogui.hotkey('alt','space','X')
time.sleep(1)
pyautogui.moveTo(24,941)
pyautogui.click(button='left')
time.sleep(2)
pyautogui.moveTo(95,925)
time.sleep(2)
pyautogui.click(button='left')

time.sleep(2)
#전자결재클릭
pyautogui.moveTo(73,322)
pyautogui.click(button='left')


#결재대기문서클릭
pyautogui.moveTo(215,299)
pyautogui.click(button='left')

#결재문서제목클릭
pyautogui.moveTo(776,277)
pyautogui.click(button='left')

#기안자복사
pyautogui.moveTo(514,321, 2)
pyautogui.dragTo(462,319, 2)
pyautogui.hotkey('ctrl','c')
pyautogui.hotkey('win','r')
pyautogui.write("notepad")
pyautogui.press("enter")
pyautogui.hotkey('ctrl','v')
time.sleep(2)

# #근무일시 복사
# pyautogui.moveTo(480,505, 2)
# pyautogui.dragTo(543,505, 2)
# pyautogui.hotkey('ctrl','c')
# time.sleep(2)

# #근무시작시간복사
# pyautogui.moveTo(505,520, 2)
# pyautogui.dragTo(482,519, 2)
# pyautogui.hotkey('ctrl','c')
# time.sleep(2)

# #근무종료시간복사
# pyautogui.moveTo(535,519, 2)
# pyautogui.dragTo(512,520, 2)
# pyautogui.hotkey('ctrl','c')
# time.sleep(2)

# #총근무시간복사
# pyautogui.moveTo(651,498, 2)
# pyautogui.dragTo(622,499, 2)
# pyautogui.hotkey('ctrl','c')
# time.sleep(2)

# #근무내용복사
# pyautogui.moveTo(712,491, 2)
# pyautogui.dragTo(1025,533, 2)
# pyautogui.hotkey('ctrl','c')
# time.sleep(2)