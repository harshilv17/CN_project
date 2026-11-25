# PF rollback (run separately on Mac 1 and Mac 3)

```bash
# before the experiment
sudo cp /etc/pf.conf /etc/pf.conf.cn-phase2-backup
sudo pfctl -sr > ~/pf-rules-before-phase2.txt

# enable PF only if it was off; SAVE the token it prints
sudo pfctl -E            # -> Token : <number>

# rollback
sudo cp /etc/pf.conf.cn-phase2-backup /etc/pf.conf
sudo pfctl -f /etc/pf.conf
sudo pfctl -sr           # only Apple's default anchors should remain
sudo pfctl -X <the-real-token-from-pfctl-E>   # NOT the literal text YOUR_SAVED_TOKEN
```

Never `pfctl -F all`. Tokens seen in the evidence screenshots: see README "Known gaps".
