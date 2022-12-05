# Tools

### **SPEEDTEST**

Install Speedtest         

```bash
brew install speedtest-cli

```

Run:                        

```bash
speedtest-cli
```

### **YOUTUBE-DL**

Install youtube-dl:       

```bash
brew install youtube-dl
```

Install ffmpeg:           

```bash
brew install youtube-dl ffmpeg
```

Download highest-res vid:   

```bash
youtube-dl -f bestvideo+bestaudio ‘link’
```

Help:                       

```bash
youtube-dl --help
```

### **IMAGEMAGICK**

Install ImageMagick:      

```bash
brew install imagemagick
```

Add border (sample):        

```bash
convert testing.png -border 1x1 -bordercolor black result.png
```

Resize (sample):            

```bash
convert testing.png -resize 1920 (or x1080) example.png
```

Add effect (sample):        

```bash
convert testing.png -charcoal 2 example.png
```

Change multiple (sample):   

```bash
for file in *.png; do convert $file -resize 1920 small-$file; done
```

Help:                       

```bash
convert help
```