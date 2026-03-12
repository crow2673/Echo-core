import requests, time, re
w = "0x400ec5a2ff6afbd42d169a86ae0cac5dcd4db296"
while 1:
  p = requests.get(f"https://polygonscan.com/address/{w}").text
  gl = re.search(r'GLM</span>[\s\w,.<>]*?([\d,]+)', p)
  print(f"💰 GLM: {gl.group(1) if gl else 0}")
  time.sleep
