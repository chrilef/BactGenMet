import sys, os, string, re
from functools import reduce
sys.path.append(os.path.join("..","lib"))
import blast, file_io, tools, progressbar

##############################################################################################################
class Motif:
    def __init__(self,reference,binpath,tmppath,word,modbase_location,reverse_modbase_location=0,
                score_cutoff=21,promoter_length=0,context_mismatches=0,motif_mismatch="No",filtered_loci=[],flg_show_methylated_sites=True):
        self.oIO = file_io.IO()
        self.flg_show_methylated_sites = flg_show_methylated_sites
        self.filtered_loci = filtered_loci
        self.oBlast = None
        self.reference = reference
        self.binpath = binpath
        self.source_path = tmppath
        self.word = word
        self.modbase_location = str(modbase_location)
        self.reverse_modbase_location = str(reverse_modbase_location)
        self.score_cutoff = 21
        try:
            self.score_cutoff = int(score_cutoff)
        except:
            path
        self.promoter_length = int(promoter_length)
        self.context_mismatches = context_mismatches
        self.motif_mismatch = motif_mismatch
        self.output_table = []              # Output table
        self.loci_in_refseq = []            # Canonical motifs found in the reference sequence
        self.loci_in_GFF = []               # Canonical motifs found in GFF and passed through filterring
        self.filtered_loci_in_refseq = []   # Canonical motifs of the reference sequence passed through filtering
        self.modified_loci_in_GFF = []      # Canonical motifs overlapping with not masked loci of the reference sequence and modified
        self.unmodified_loci_in_GFF = []    # Canonical motifs overlapping with not masked loci of the reference sequence and not modified
        self.masked_loci_in_refseq = []     # Canonical motifs found in GFF overlapping masked loci of the reference sequence
        self.masked_loci_in_GFF = []        # Canonical motifs overlapping with not masked loci of the reference sequence
        self.novel_GFF_modpredictions = []  # Novel modified sites predicted in GFF, which were not present in refseq
        self.not_found_loci = []            # Modified motifs in GFF file, which were not found in the reference sequence
        self.num_instances = 0              # Number of canonical motifs found in GFF file, which match to the refseq and not masked
        self.num_found_sites = 0            # Number of found modified/unmodified canonical motifs
        self.table_titles = ['Motif','Strand','Location','Match','Description','Annotation']
        self.success = False
        
    def __str__(self):
        return self.tostring()
    
    def _set_loci(self,motif,wlength,seq):
        #self.loci_in_refseq = re.findall(motif,seq)
        tools.msg("\tSearching for instances of motifs...")
        #### This is done in reset()
        self.loci_in_refseq = []
        self.masked_loci_in_refseq = []
        p = 0
        while p < len(seq)-1:
            locus = re.search(motif,seq[p:])
            if not locus:
                break
            p += locus.span()[0]
            if p < len(seq)/2:
                self.loci_in_refseq.append([p+1,p+wlength,"+"])
            else:
                self.loci_in_refseq.append([len(seq)-p-wlength+1,len(seq)-p,"-"])
            p += 1
        self.filtered_loci_in_refseq = self.get_available_loci()
        self.masked_loci_in_refseq = list(filter(lambda locus: locus not in self.filtered_loci_in_refseq, self.loci_in_refseq))
    
    def _cutoff(self,ft):
        if self.filtered_loci != [] and self.overlap_with_filtered_regions(int(ft.location.start)):
            return False
        description = tools.get_modbase_description(ft)
        if not description or "score" not in description:
            return True
        try:
            score = float(description['score'])
        except:
            return True
        if self.score_cutoff <= score:
            return True
        return False
    
    def _fitting(self,entry):
        score = int(entry['score'])
        if self.score_cutoff <= score:
            return True
        return False

    def _masking(self,entry):
        if self.filtered_loci != [] and self.overlap_with_filtered_regions(entry["start"]):
            return True

    def execute(self,gff_infile,gbk_infile=""):
        if not os.path.exists(gff_infile):
            return
        gff = self.oIO.readGFF(gff_infile)
        if not gff["Body"]:
            return
        gbk = None
        if os.path.exists(gbk_infile):
            try:
                gbk = self.oIO.readGBK(gbk_infile)
            except:
                gbk = None
                pass
        self.output_table = self.search(gff,gbk,tools.compile_motif(self.word),len(self.word),
            self.modbase_location,self.reverse_modbase_location,self.promoter_length)
        motif = tools.generate_motif(len(self.word),list(map(lambda item: item['Motif'], self.output_table)))
        self.output_table.insert(0,["%s\n%s%s modified at %s; " % (self.reference,self.get_run_statistics(),motif,self.modified_sites()),"%d/%d" % (self.num_found_sites,self.num_instances),"\n"])
        self.success = True
        return self.success
    
    def get_run_statistics(self):
        statistics = [
            "Number of sites found in reference sequence: %d" % len(self.loci_in_refseq),
            "Number of filtered sites in reference sequence after masking: %d" % len(self.filtered_loci_in_refseq),
            "Number of sites found in GFF file: %d" % len(self.loci_in_GFF),
            "Number of masked sites taken from GFF file: %d" % len(self.masked_loci_in_GFF),
            "Number of sites prdecited in GFF file and not found: %d" % len(self.not_found_loci),
            "Number of sites found in GFF file, which were not present in the reference sequence: %d" % len(self.novel_GFF_modpredictions),
            "Total number of instances: %d" % self.num_instances,
            "Number of modified sites: %d" % len(self.modified_loci_in_GFF),
            "Number of unmodified sites: %d" % len(self.unmodified_loci_in_GFF),
        ]
        return "\n"+"\n".join(statistics)+"\n"
     
    def modified_sites(self):
        if self.reverse_modbase_location != "0":
            return "%s and %s" % (self.modbase_location,self.reverse_modbase_location)
        return str(self.modbase_location)
        
    def tostring(self):
        if not self.success:
            return ""
        table = [self.output_table[0],self.table_titles]
        table += list(map(lambda i: list(map(lambda key: self.output_table[i][key], self.table_titles)), range(1,len(self.output_table),1)))
        return "\n".join(map(lambda item: "\t".join(item), table))
    
    def get_word(self):
        return self.word
    
    def get_modbase_location(self):
        return self.modbase_location
    
    def get_rev_modbase_location(self):
        return self.reverse_modbase_location

    def get_modbase_dict(self):
        def get_color(is_matched):
            if is_matched == "Yes":
                return "blue"
            elif is_matched == "None":
                return "green"
            return "red"
        def get_strand(strand):
            if strand == "DIR":
                return "1"
            return "-1"
        
        modbases = {}
        for i in range(1,len(self.output_table)):
            item = self.output_table[i]
            moltype,dir,score,coverage,SC_rel_location = item['Description'].split("|")[0].split("\t")
            modbases[i-1] = [item['Location'],
                            get_color(item['Match']),get_strand(item['Strand']),
                            ["%s\t%s\t%s\t%s\t%s" % (item['Location'],moltype,score,coverage,item['Motif'])]
                ]
        return modbases

    def get_strand(self,strand,complement_site=False):
        if (strand == 1 and not complement_site) or (strand == -1 and complement_site):
            return "DIR"
        return "REV"

    def get_annotation(self,gene,strand=0):
        if gene == "non-coding":
            return gene
        description = "[%d..%d]" % (int(gene.location.start),int(gene.location.end))
        if 'locus_tag' in gene.qualifiers:
            description = "%s %s" % (gene.qualifiers['locus_tag'][0],description)
        if 'gene' in gene.qualifiers:
            description += "; %s" % gene.qualifiers['gene'][0]
        if 'product' in gene.qualifiers:
            description += "; %s" % gene.qualifiers['product'][0]
        
        if not strand or gene.strand == strand:
            description += "\tPLUS"
        else:
            description += "\tMINUS"
        
        if 'promoter' in gene.qualifiers:
            description += "\tPROMOTER"

        return description

    def overlap(self,cds,start,promoter):
        if ((cds.strand==1 and start <= int(cds.location.end) and start >= int(cds.location.start)-promoter) or
            (cds.strand==-1 and start <= int(cds.location.end)+promoter and start >= int(cds.location.start))):
            if start <= int(cds.location.end) and start >= int(cds.location.start):
                return cds
            cds.qualifiers['promoter'] = ["Yes"]
            return cds
        return
    
    def overlap_with_filtered_regions(self,location):
        for locus in self.filtered_loci:
            if location >= locus[0] and location < locus[1]:
                return True
        return False

    def get_site(self,entry,length,k,promoter,genes,complement_site,motif=""):
        cds = []
        strand = 1
        if entry['strand'] == "-":
            strand = -1
        cds =["nd"]
        description = ""
        if not motif:
            motif = entry["data"]["context"][21-k:21-k+length]
            if complement_site:
                motif = tools.reverse_complement(motif)
            
            if strand == 1:
                location = "%d..%d" % (int(entry['start'])-k+1,int(entry['start'])-k+length)
            else:
                location = "%d..%d" % (int(entry['start'])+k-length,int(entry['start'])+k-1)
        else:
            location = "%d..%d" % (int(entry['start']),int(entry['end']))
        if genes:
            cds = list(filter(lambda ft: self.overlap(ft,int(entry['start']),promoter) and ft.strand==strand, genes))
            if not cds:
                cds =["non-coding"]
            annotation = "|".join(map(lambda gene: self.get_annotation(gene,strand), cds))
        return dict(zip(self.table_titles,
                [motif,self.get_strand(strand,complement_site),location,entry['match'],"%s\t%s\t%s\t%s\t%s" % 
                (entry['modtype'],self.get_strand(strand,complement_site),str(entry['score']),str(entry["data"]['coverage']),
                str(tools.get_site_location_relative_to_start_codon(cds,location,strand,int(self.modbase_location),int(self.reverse_modbase_location)))),
                annotation]))
                
    def dereplicate_sites(self,ls):
        if len(ls) < 2:
            return ls
        ls.sort(key=lambda d: d['Strand']+d['Location'])
        for i in range(len(ls)-1,0,-1):
            if (ls[i]["Strand"]+ls[i]["Location"]==ls[i-1]["Strand"]+ls[i-1]["Location"] or
                (i > 1 and ls[i]["Strand"]+ls[i]["Location"]==ls[i-2]["Strand"]+ls[i-2]["Location"])):
                del ls[i]
        return ls

    def find_context(self,entry,seq,occupied_sites):
        context = entry["data"]["context"]
        word = entry['word']
        start = int(entry['start'])
        strand = entry['strand']
        locations = []
        p = seq.find(context)
        if p > -1:
            locations.append(p)
        while p != -1:
            p = seq.find(context,p+1)
            if p > -1:
                locations.append(p)
        for i in range(len(locations)-1,-1,-1):
            p = locations[i]
            if (p >= len(context)+len(seq)//2 and ("%s%d..%d" % (strand,len(seq)-p-len(context)+1,len(seq)-p)) not in occupied_sites):
                locations[i] = [len(seq)-p-len(context)//2,"-",len(seq)-p-len(context)+1,len(seq)-p]
            elif ("%s%d..%d" % (strand,p+1,p+len(context))) not in occupied_sites:
                locations[i] = [p+1+len(context)//2,"+",p+1,p+len(context)]
            else:
                del locations[i]
        if len(locations) > 1:
            list(map(lambda ls: ls.insert(0,abs(int(entry['start'])-ls[0])), locations))
            locations.sort()
            start,strand = locations[0][1:3]
            occupied_sites.append("%s%d..%d" % (strand,locations[0][3],locations[0][4]))
            return start,strand
        elif len(locations)==1:
            start,strand = locations[0][:2]
            occupied_sites.append("%s%d..%d" % (strand,locations[0][2],locations[0][3]))
            return start,strand
        return 0,strand

    def match(self,seq,entry,n,occupied_sites,dbname):        
        start,strand = self.find_context(entry,seq,occupied_sites)
        if start:
            return start,strand,True
        seq = seq[:len(seq)/2]
        context = entry["data"]["context"]
        context_file = "%s_record.fa" % dbname
        self.oIO.save(">record %d\n%s" % (n,context),os.path.join(self.source_path,context_file))
        fasta_file = dbname+".fa"
        if not os.path.exists(os.path.join(self.source_path,fasta_file)):
            self.oIO.save(">genome\n%s" % seq,os.path.join(self.source_path,fasta_file))
            self.oBlast.create_db(fasta_file,dbname)
        self.oBlast.execute(context_file,dbname)
        hsps = list(filter(lambda hsp: "%s%d..%d" % (hsp.get_strand(),hsp.sbjct_start,hsp.sbjct_end) not in occupied_sites, self.oBlast.get_matches(len(context),self.context_mismatches)))
        if not hsps:
            return 0,0,False
        matches = list(filter(lambda hsp: hsp.sbjct.upper().find(entry['word'].upper()) > -1, hsps))
        if not matches:
            matches = hsps
        if len(matches) > 1:
            matches = list(map(lambda hsp: [len(context)-hsp.identities,hsp.measure_distance(entry['start'],len(context)//2),hsp], matches))
            matches.sort()
            matches = list(map(lambda ls: ls[-1], matches))
        top_match = matches[0]
        strand = top_match.get_strand()
        if strand == "+":
            start = int(top_match.sbjct_start-top_match.query_start+1+len(context)//2)
        else:
            start = int(top_match.sbjct_end+(len(context)-top_match.query_end)+len(context)//2)
        occupied_sites.append("%s%d..%d" % (strand,top_match.sbjct_start,top_match.sbjct_end))
        return start,strand,top_match.sbjct.upper().find(entry['word'].upper()) > -1
        
    def search(self,gff,gbk,motif,length,direct="",reverse="",promoter=0):
        ls = []
        if not gff or "Body" not in gff or not gff["Body"]:
            return 0,ls
        no_match = 0
        points = []
        if direct:
            points += list(map(lambda v: int(v), direct.split(",")))
        if reverse:
            points += list(map(lambda v: -int(v), reverse.split(",")))
        points = list(filter(lambda v: v, points))
        motifs = tools.inlist_motifs(motif)
        remotifs = []
        if reverse and reverse != "0":
            remotifs = tools.inlist_motifs(motif,True)
        genes = []
        #### All this done in self.reset()
        seq = ""
        self.loci_in_refseq = []
        self.not_found_loci = []
        self.loci_in_GFF = []
        self.masked_loci_in_GFF = []
        self.modified_loci_in_GFF = []
        no_match = 0
        
        if gbk:
            genes = list(filter(lambda ft: ft.type=="CDS", gbk.features))
            seq = str(gbk.seq)+str(gbk.reverse_complement().seq)
            #seq += tools.reverse_complement(seq)
            if not self.loci_in_refseq:
                self._set_loci(motif,length,seq)
            self.oBlast = blast.BLAST("dna",self.binpath,self.source_path)
            random_file_name = tools.get_random_filename(self.source_path)
        for k in points:
            occupied_sites = []
            ls.append([])
            searched_motifs = motifs
            rem = "%d's %s" % (k,motif[abs(k)-1])
            complement_site = False
            if k < 0:
                complement_site = True
                k += (len(self.word)+1)
                searched_motifs = remotifs
                rem = "rev_%d's %s" % (k,tools.reverse_complement(motif)[k-1])
            p = 21 - k
            dif = maxdif = last_start = 0
            message = "%s at %s: " % (motif,rem)
            if len(message) > 30:
                message = "Run"
            canonical_motifs = list(filter(lambda entry: entry["data"]["context"][p:p+length] in searched_motifs, gff["Body"]))
            if not len(canonical_motifs):
                tools.alert(f"Canonical motif {motif} was not found among modified sites!")
                print(searched_motifs)
                break
            bar = progressbar.indicator(len(canonical_motifs),message)
            for i in range(len(canonical_motifs)):
                entry = canonical_motifs[i]
                entry['word'] = entry["data"]["context"][p:p+length]
                self.loci_in_GFF.append(entry)
                if self._masking(entry):                    
                    self.masked_loci_in_GFF.append(entry)
                    bar(i)
                    continue
                if gbk:
                    location,strand,match = self.match(seq,entry,i,occupied_sites,random_file_name)
                    if not location or (self.motif_mismatch=="No" and not match):
                        entry['match'] = "No"
                        self.not_found_loci.append(self.get_site(entry,length,k,promoter,genes,complement_site))
                        bar(i)
                        continue
                    d = int(entry['end'])-int(entry['start'])
                    entry['start'] = location
                    entry['end'] = location+d
                    entry['strand'] = strand
                    entry['site'] = seq[entry['start']-1:entry['end']]
                    if self._masking(entry):
                        self.masked_loci_in_GFF.append(entry)
                        bar(i)
                        continue
                    if not self._fitting(entry):
                        self.unmodified_loci_in_GFF.append(entry)
                        bar(i)
                        continue
                    if strand == "-":
                        entry['site'] = tools.reverse_complement(entry['site'])
                    if match:
                        entry['match'] = "Yes"
                    else:
                        entry['match'] = "No"
                        no_match += 1
                
                site = self.get_site(entry,length,k,promoter,genes,complement_site)
                if site:
                    self.modified_loci_in_GFF.append(entry)
                    ls[-1].append(site)
                else:
                    self.not_found_loci.append(entry)
                bar(i)
            bar.stop()
            ls[-1]=self.dereplicate_sites(ls[-1])
            self.modified_loci_in_GFF = list(map(lambda site: site, ls[-1]))
            all_sites = list(map(lambda ls: "%s%d..%d" % (ls[2],ls[0],ls[1]), self.filtered_loci_in_refseq))
            methylated_site_locations = list(map(lambda ls: ls["Strand"].replace("DIR","+").replace("REV","-")+ls["Location"], ls[-1]))
            self.novel_GFF_modpredictions = list(filter(lambda s: s not in all_sites, methylated_site_locations))
            
            if not self.flg_show_methylated_sites:
                ls[-1] = self.get_nonmethylated_sites(ls[-1],seq,length,k,promoter,genes)
            self.clean(self.source_path,random_file_name)
            
        self.num_instances = len(self.filtered_loci_in_refseq)+len(self.novel_GFF_modpredictions) # Filtered sites in refseq plus modifications newly predicted in GFF
        
        if not points:
            ls.append(self.get_nonmethylated_sites([],seq,length,0,promoter,genes))
        if self.flg_show_methylated_sites and points:
            self.num_found_sites = len(self.modified_loci_in_GFF)
            ls = self.select_overlaps(ls,points)
        else:
            if len(ls) > 1:
                ls = reduce(lambda ls1,ls2: ls1+ls2, ls)
            else:
                ls = ls[0]
            #self.num_found_sites = len(self.unmodified_loci_in_GFF)
            if len(ls) != len(self.unmodified_loci_in_GFF):
                raise IOError("Mismatch error %d != %d!" % (len(ls),len(self.unmodified_loci_in_GFF)))
            self.num_found_sites = len(self.unmodified_loci_in_GFF)
        return ls
    
    def get_nonmethylated_sites(self,methylated_sites,seq,length,k,promoter,genes):
        def get_word(seq,ls):
            seq = seq[int(ls[0])-1:int(ls[1])]
            if ls[2] == "-":
                return tools.reverse_complement(seq.upper())
            return seq.upper()
        
        methylated_site_locations = list(map(lambda ls: ls["Strand"].replace("DIR","+").replace("REV","-")+ls["Location"], methylated_sites))
        unmethylated_sites = list(filter(lambda ls: "%s%d..%d" % (ls[2],ls[0],ls[1]) not in methylated_site_locations, self.filtered_loci_in_refseq))
        
        self.unmodified_loci_in_GFF += list(map(lambda ls: dict(zip(['word','start','end','strand','score','modtype','match','data'],
            [get_word(seq,ls),int(ls[0]),int(ls[1]),ls[2],0,"not modified","None",{'context':"",'coverage':'na'}])), unmethylated_sites))
        self.unmodified_loci_in_GFF =  list(map(lambda entry: self.get_site(entry,length,k,promoter,genes,None,entry['word']), self.unmodified_loci_in_GFF))
        self.unmodified_loci_in_GFF = self.dereplicate_sites(list(filter(lambda site: site, self.unmodified_loci_in_GFF)))
        return self.unmodified_loci_in_GFF
    
    def get_available_loci(self):
        return list(filter(lambda locus: not self.overlap_with_filtered_regions(int(locus[0])), self.loci_in_refseq))
        
    def get_all_motif_entries(self,seq):
        ls = []
        if not seq:
            return ls
        p = 0
        for w in self.loci_in_refseq:
            p = seq.find(w,p+1)
            if p < len(seq)/2:
                start = p+1
                end = p+len(w)
            else:
                start = len(seq)-p
                end = start + len(w) - 1
            if not self.overlap_with_filtered_regions(start):
                ls.append([start,end])
        return ls
    
    def get_description(self):
        return "%s,%s,%s" % (self.word,self.modbase_location,self.reverse_modbase_location)
    
    def select_overlaps(self,ls,points):
        selection = list(map(lambda entry: dict(zip(entry.keys(),entry.values())), ls[0]))
        if len(ls) > 1:
            for i in range(1,len(ls),1):
                loci = list(map(lambda item: item['Location'], ls[i]))
                for j in range(len(selection)-1,-1,-1):
                    if selection[j]['Location'] not in loci:
                        del selection[j]
        return selection
        
    def clean(self,path,generic_name):
        fnames = list(filter(lambda fn: fn.find(generic_name) > -1, os.listdir(path)))
        for fname in fnames:
            os.remove(os.path.join(path,fname))
            
    def reset(self):
        self.output_table = []              # Output table
        self.loci_in_refseq = []            # Canonical motifs found in the reference sequence
        self.loci_in_GFF = []               # Canonical motifs found in GFF and passed through filterring
        self.filtered_loci_in_refseq = []   # Canonical motifs of the reference sequence passed through filtering
        self.modified_loci_in_GFF = []      # Canonical motifs overlapping with not masked loci of the reference sequence and modified
        self.unmodified_loci_in_GFF = []    # Canonical motifs overlapping with not masked loci of the reference sequence and not modified
        self.masked_loci_in_refseq = []     # Canonical motifs found in GFF overlapping masked loci of the reference sequence
        self.masked_loci_in_GFF = []        # Canonical motifs overlapping with not masked loci of the reference sequence
        self.not_found_loci = []            # Modified motifs in GFF file, which were not found in the reference sequence
        self.num_instances = 0              # Number of canonical motifs found in GFF file - not found motifs
        self.num_found_sites = 0            # Number of found modified/unmodified canonical motifs
        self.oBlast = None
       
