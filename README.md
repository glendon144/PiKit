# PiKit – Engelbart Demo Kit

PiKit is a cross-platform desktop tool for exploring “hyper-documents” in the spirit of Douglas Engelbart’s NLS and Ted Nelson’s Xanadu.  
It lets you **store / ask / link / image-generate** in a single Tkinter GUI.

| Feature | Description |
|---------|-------------|
| **ASK** | Send a selected text passage to your GPT-powered backend and store the reply as a new document, auto-linking back to the quote. |
| **IMAGE** | Generate a DALL-E (or SD) image from selected text. First click shows a thumbnail; click again to enlarge / save. |
| **BACK** | Navigate history or collapse an enlarged image. |
| **Context-menu & Toolbar** | Right-click or hit the buttons for the same actions. |
| **Import / Export** | Plain-text files in, plain-text files (or PNG images) out. |


If desired, copy the sample database into the storage folder.

I have this up and running on a Raspberry Pi 4, A BTX B1-Pro Micro PC running Windows 11, An M1-based Mac Mini running Sequoia, and a 2011 iMac running High Sierra, and a 32-bit Intel Ubuntu 18 system.   The requirements for the Mac were installed with homebrew and somtimes with MacPorts.  The trickiest thing on all platforms seems to be getting a reasonable version of python installed that supports tkinter (the tcl-tk based GUI library.)   Ubuntu typically ships with a version of python that does not support tkinter, so sometimes it has to be built from source.  Also, the OpenAI library works great as a backend, as long as you pin the installation to version 0.28 as follows:

$pip install openai==0.28

The other requirements are pillow and requests, which can be tricky on some platforms.  Pillow requires numpy, and
the version of numpy can be too new to support some 32 bit platforms.  But I did get it running on a 32 bit Ubuntu 18 system!

## Quick start

```bash
git clone git@github.com:glendon144/PiKit.git
cd PiKit
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt        # Tkinter, Pillow, openai, ...
python main.py




WARNING:  This program can be addictive and is lots of fun!  Thanks for trying it out.  If you have
any questions or concerns, please email glendon144@gmail.com   I can also be reached on Facebook and YouTube.
Enjoy, in the original spirit of Doug Engelbart! :-)
