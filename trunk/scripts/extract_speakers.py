#!/usr/bin/env python 

from multiprocessing import Process, cpu_count, active_children
import os
import shlex, subprocess
import sys, signal
import time
import re
p = None
clusters = {}

def termHandler(a,b):
	print "termHandler"
	p.kill()

signal.signal(signal.SIGINT, termHandler )

dev_null = open('/dev/null','w')

def humanize_time(secs):
	mins, secs = divmod(secs, 60)
	hours, mins = divmod(mins, 60)
	return '%02d:%02d:%02d,%s' % (hours, mins, int(secs), str(("%0.3f" % secs ))[-3:] )

def seg2trim(segfile):
	basename, extension = os.path.splitext(segfile)
	s = open(segfile,'r')
	for line in s.readlines():
		if not line.startswith(";;"):
			arr = line.split()
			clust = arr[7]
			st = float(arr[2])/100
			end = float(arr[3])/100
			try:
				os.makedirs("%s/%s" % (basename, clust) )
			except os.error as e:
				if e.errno == 17:
					pass
				else:
					raise os.error
			commandline = "sox %s.wav %s/%s/%s_%s.wav trim  %s %s" % ( basename, basename, clust, clust, st, st, end )
			args = shlex.split(commandline)
			p = subprocess.Popen(args)
			retval = p.wait()
			if retval != 0:
				raise Exception("Subprocess closed unexpectedly "+str(p) )
	s.close()

def seg2srt(segfile):
	def readl(s):
		total = []
		for line in s.readlines():
			if not line.startswith(";;"):
				arr=line.split()
				total.append(arr)
		s.close()
		return total

	def readtime(aline):
		return int(aline[2])

	basename, extension = os.path.splitext(segfile)	
	s = open(segfile,'r')
	lines=readl(s)
	lines.sort(key=readtime, reverse=False)
        fileoutput = basename+".srt"
	FILE = open(fileoutput,"w")
	row = 0
	for line in lines:
		row = row +1
		FILE.write(str(row)+"\n")
		FILE.write(humanize_time(float(line[2])) + " --> " + humanize_time(float(line[2])+float(line[3]))+"\n")
		FILE.write(line[7]+"\n")
		FILE.write(""+"\n")
			
	FILE.close()


def replace_words(text, word_dic):
    """
    take a text and replace words that match a key in a dictionary with
    the associated value, return the changed text
    """
    rc = re.compile('|'.join(map(re.escape, word_dic)))
	
    def translate(match):
        return word_dic[match.group(0)]+'\n'
    
    return rc.sub(translate, text)

def video2trim(videofile):
	commandline = "./video2trim.sh %s" %  videofile
	args = shlex.split(commandline)
	p = subprocess.Popen(args)
	retval = p.wait()
	if retval != 0:
		raise Exception("Subprocess closed unexpectedlyi "+str(p) )


def srt2subnames(original_subtitle, showname, key_value):
	key_value=dict(map(lambda (key, value): (str(key)+"\n", value), key_value.items()))
	str3 = replace_words(original_subtitle, key_value)
	out_file = showname+"_new.srt"
	# create a output file
	fout = open(out_file, "w")
	fout.write(str3)
	fout.close()	

def extract_clusters(filename):
	f = open(filename,"r")
	for l in f:
		 if l.startswith(";;") :
			ll = l.split()[1].split(':')[1]	
			clusters[ll] = {}
	f.close()

def mfcc_vs_gmm(showname, gmm):
	commandline = 'java -Xmx2G -Xms2G -cp ./LIUM_SpkDiarization.jar  fr.lium.spkDiarization.programs.MScore --sInputMask=%s.seg   --fInputMask=%s.mfcc  --sOutputMask=%s.ident.'+gmm+'.seg --sOutputFormat=seg,UTF8  --fInputDesc="audio16kHz2sphinx,1:3:2:0:0:0,13,1:0:300:4" --tInputMask=./gmm_db/'+gmm+' --sTop=8,ubm.gmm  --sSetLabel=add --sByCluster '+  showname 
	args = shlex.split(commandline)
	p = subprocess.Popen(args)
	retval = p.wait()
	if retval != 0:
		raise Exception("Subprocess closed unexpectedlyi "+str(p) )

def manage_ident(showname, gmm):
	f = open("%s.ident.%s.seg" % (showname,gmm ) ,"r")
	for l in f:
		 if l.startswith(";;"):
			cluster, speaker = l.split()[ 1 ].split(':')[ 1 ].split('_')
			i = l.index('score:'+speaker) + len('score:'+speaker+" = ")
			ii = l.index(']',i) -1
			value = l[i:ii]
			if clusters[ cluster ].has_key( speaker ) == False:
				clusters[ cluster ][ speaker ] = float(value)
			else:
				if clusters[ cluster ][ speaker ] < float(value):
					clusters[ cluster ][ speaker ] = float(value)
	f.close()

def wave_duration(wavfile):
	import wave
	w = wave.open(wavfile)
	p = w.getparams()
	w.close()
	return p[3]/p[2]


if __name__ == '__main__':
	cpus = cpu_count()
	print '%s processors' % cpus
	start_time = time.time()
	file_input = sys.argv[ 1: ] 
	print file_input
	if len( file_input ) > 1: #blanks in file name
		print file_input
		new_file_input = '_'.join(file_input).replace("'",'_').replace('-','_')
		os.rename(' '.join(file_input),new_file_input)
		file_input = new_file_input
	else:
		new_file_input = file_input[0].replace("'",'_').replace('-','_').replace(' ','_')
		os.rename( file_input[0], new_file_input )
	file_input = new_file_input

	video2trim( file_input )
	basename, extension = os.path.splitext( file_input )
	
	extract_clusters( "%s.seg" %  basename )
	p = {}
	for f in os.listdir('./gmm_db'):
		#print "len(active_children()) %d" % len(active_children() )
		if f.endswith('.gmm') and len(active_children()) < (cpus-1) :
			p[f] = Process(target=mfcc_vs_gmm, args=( basename, f ) )
			p[f].start()
		else:
			while len(active_children()) >= cpus:
				#print "len(active_children()) %d" % len(active_children() )
				time.sleep(1)	
			p[f] = Process(target=mfcc_vs_gmm, args=( basename, f ) )
			p[f].start()
			#mfcc_vs_gmm( basename, f )
	for proc in p:
		if p[proc].is_alive():
			print 'joining proc %s' % str(proc)
			p[proc].join()	
	
	#print "Processes %s" % active_children()
	for f in os.listdir('./gmm_db'):
		if f.endswith('.gmm'):
			manage_ident( basename, f )
	print ""
	speakers = {}
	print clusters
	for c in clusters:
	    print c
	    value = -33.0
	    best = 'unknown'
            speakers[c] = 'unknown'
	    for cc in clusters[c]:
		if clusters[c][cc] > value:
			value = clusters[c][cc]
			best = cc
			speakers[c] = cc
		print "\t %s %s" % (cc , clusters[c][cc])
	    print '\t ------------------------'
	    array = clusters[c].values()
	    array.sort()
	    array.reverse()
	    distance = abs(array[1]) - abs(array[0])
	    mean = sum(array) / len(array)
	    m_distance = abs(mean) - abs(array[0])
            if distance < .1 :
		    best = 'unknown'
		    speakers[c] = best
	    print '\t best speaker: %s (distance from 2nd %f - mean %f - distance from mean %f ) ' % (best , distance, mean, m_distance)
	file_original_subtitle = open(basename+".srt")
        srt2subnames(file_original_subtitle.read(), basename, speakers)
	sec = wave_duration(basename+'.wav')
	total_time = time.time() - start_time
	print "\nwav duration: %s\nall done in %dsec (%s) with %s cpus" % ( time.strftime('%H:%M:%S',time.gmtime(sec)), total_time,  time.strftime('%H:%M:%S', time.gmtime(total_time)), cpus )
