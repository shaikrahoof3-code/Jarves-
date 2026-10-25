JARVIS WEB UI - HOW TO RUN
==========================

IMPORTANT FOR iPAD
  An iPad cannot run Jarvis itself (Python does not run there).
  Jarvis runs on a Windows or Mac computer, and your iPad Air opens it as a web page.

NO pip install NEEDED. Only Python.

STEP 1. Install Python (one time)
  python.org/downloads. WINDOWS: tick "Add Python to PATH".

STEP 2. Get a free key (one time)
  console.groq.com > sign up > API Keys > Create > copy it.

STEP 3. Unzip, then open a terminal inside the folder
  Windows: open the folder, click the address bar, type  cmd  , press Enter.
  Mac: right-click the folder > New Terminal at Folder.

STEP 4. Put your key in
  Windows:  copy .env.example .env     then   notepad .env
  Mac:      cp .env.example .env       then   open -e .env
  Replace  paste-your-free-key-here  with your key. Save.

STEP 5. Check (optional)
  python test_jarvis.py       -> should print ALL TESTS PASSED

STEP 6. Start
  On the computer itself (opens the browser by itself, port 8080):
      python jarvis.py
  For your iPad (same Wi-Fi as the computer):
      python jarvis.py --lan
  Open the long link it prints, in Safari on the iPad.
  Keep the terminal window open while you use Jarvis.

THE SCREEN
  Top: 4 checks. The microphone button stays locked until the key and the AI service work.
  Then tap "Enable microphone". The browser asks your permission. Nothing listens before that.
  While asleep, nothing you say is sent to Jarvis except "Wake up Jarvis".
  When Jarvis wants to run a command, a box asks Allow or Deny.

IPAD MICROPHONE (be aware)
  Safari only allows the microphone on secure pages. The plain --lan link is not secure, so
  the Enable microphone button will tell you so. Two ways:
   A) Easy and always works: tap the text box and use the microphone key on the iPad keyboard
      (dictation), then Send.
   B) Try the secure mode:   python jarvis.py --lan --https
      Safari shows a warning (the certificate is made by you, on your own computer).
      Tap Show Details > visit this website. Then try Enable microphone.
      I could not test this on a real iPad, so it may still refuse. Use A if so.

VIDEO EDITING
  Install ffmpeg (ffmpeg.org). Put the video into the  workspace  folder.
  Say or type: "Cut the first 10 seconds off intro.mp4".
  Premiere and VN on the iPad cannot be controlled by Jarvis.

LEARNING
  Corrections and preferences are saved in  memory.md  and used every time after.

SAFETY
  - The link has a secret key (file .token). Do not share the link.
  - Jarvis can only save files inside  workspace  .
  - Use --lan only on a Wi-Fi you trust (home).

LIMITS
  - The free service has daily limits. If answers stop, wait, or change MODEL in .env.
  - Voice recognition uses Apple's or Google's own service inside the browser.
  - He does not retrain himself; he improves by remembering what you tell him.
