import imaplib
import email
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

#the function below is just an replacement of the proccess which will be done on the recived mail before sending it back to the sender.
def process(original_msg):
    new_msg = MIMEMultipart()
    new_msg['From'] = original_msg['To']  
    new_msg['To'] = original_msg['From']  

    new_msg['Subject'] = f"Re: {original_msg['Subject']}"
    

    return new_msg


imap_server = "imap.gmail.com"
smtp_server = "smtp.gmail.com"

#email adderres of the user
user = 'USER_MAIL_ADDRESS'
#password of the user
password = 'USER_PASSWORD'
#sender's email address
sender = "SENDER_ADDRESS"

imap = imaplib.IMAP4_SSL(imap_server)

imap.login(user,password)

imap.select("Inbox")

_, msgnums = imap.search(None,"UNSEEN","FROM",sender)


for msgnum in msgnums[0].split():
    _, data = imap.fetch(msgnum,"(RFC822)")

    msg = email.message_from_bytes(data[0][1])

    #next steps are done here:
    processed_msg = process(msg)

    #after that

    with smtplib.SMTP_SSL(smtp_server) as smtp:
        smtp.login(user, password)
        smtp.send_message(processed_msg)

imap.logout

