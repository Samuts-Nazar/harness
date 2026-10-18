import sys
a,b=int(sys.argv[1]),int(sys.argv[2])
L=open('data/witcher_books.txt',encoding='utf-8').read().split('\n')
for i in range(a-1,b):
    if L[i].strip(): print(f"{i+1}: {L[i]}")
