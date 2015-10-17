# This script wraps the innerhtml string of a page with the appropriate <html>, <head> and <body> tags.
# This would enable Tika to parse it correctly. 

import sys
import os

def list_files(dir):                                                                                                  
    r = []                                                                                                            
    subdirs = [x[0] for x in os.walk(dir)]                                                                            
    for subdir in subdirs:                                                                                            
        files = os.walk(subdir).next()[2]                                                                             
        if (len(files) > 0):                                                                                          
            for file in files:                                                                                        
                r.append(subdir + "/" + file)                                                                         
    return r 

def log(msg):
	print(msg)

def main(argv=None):
	argv = sys.argv[1:]
	try:
		inputDir = argv[0]
		outputDir = argv[1]
		appendString = argv[2]
	except:
		print("Usage <path to files> <outputDir> <file append string>")
		exit()
	log("Setting input dir as %s and outputDir as %s"%(inputDir, outputDir))
	if not os.path.exists(outputDir):
		os.makedirs(outputDir)

	files = list_files(inputDir)
	for file in files:
		with open(file,"r") as f:
			log("Processing file " + f.name)
			content = f.read()
			content = "<html><head></head><body> " + content + "</body></html>"
			outFile =  outputDir+"/" + appendString + os.path.basename(file)+".html"
			with open(outFile,"w") as out:
				log("Writing file " + os.path.basename(outFile))
				out.write(content)
				os.utime(outFile, (os.path.getctime(file), os.path.getctime(file)))
				out.close()
			f.close()



if __name__ == '__main__':
	main()