"""
urlib is used to parse my hoseted db url
"""
import os
import urllib.parse
import slugify
import psycopg2
import markdown
from os import listdir
from flask import Flask, render_template, request, abort, redirect, url_for, session, jsonify
from flask_cors import CORS
from flask_mail import Mail, Message
from werkzeug.utils import secure_filename
import boto3

app = Flask(__name__) #provide flask min info to init.
cors = CORS(app, supports_credentials=True)
mail = Mail(app)
app.secret_key = "smashyourkeyfjdsaklfjdasklfjadsklfjadsklfjadslkfjasdfnbvncnmx"

ALLOWED_EXTENSIONS = set(['txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'])

client = boto3.client(
    's3',
    aws_access_key_id = os.environ['AWS_ACCESS_KEY_ID'],
    aws_secret_access_key = os.environ['AWS_SECRET_ACCESS_KEY']
)

app.config.update(
	DEBUG=True,
	#EMAIL SETTINGS
	MAIL_SERVER='smtp.gmail.com',
	MAIL_PORT=465,
	MAIL_USE_SSL=True,
	MAIL_USERNAME = os.environ['GMAIL_PRIMARY_EMAIL'],
	MAIL_PASSWORD = os.environ['GMAIL_APP_KEY']
)

mail=Mail(app)

urllib.parse.uses_netloc.append("postgres")

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

class Blogs():
    """
    Creates connection to blogs table and sql such as inserting blog posts and deleting etc...
    
    """
    dburl = urllib.parse.urlparse('''postgres://''' + os.environ['FLASK_SQL_UNAME'] + ''':''' + os.environ['FLASK_SQL_PSWRD'] + '''@ec2-107-22-167-179.compute-1.amazonaws.com:5432/d2kv1v98ptm5je''')

    def __init__(self):
        self.conn = self.getconn(self.dburl)
        self.c = self.conn.cursor()

    def get_write(self):
        "Sets the cursor for the class"
        self.conn = self.getconn(self.dburl)
        self.c = self.conn.cursor()

    def getconn(self, url):
        "returns the connection based on the dburl in the class"
        return psycopg2.connect(
            database=url.path[1:],
            user=url.username,
            password=url.password,
            host=url.hostname,
            port=url.port
        )

    def get_all(self):
        "All blog posts"
        sql = "SELECT * from blogs"
        self.c.execute(sql)
        data = self.c.fetchall()
        output = []
        for row in data:
            single_blog = Blog(row[0], row[1], row[2], row[3], row[4], row[5])
            output.append(single_blog)
        return output

    def get_slug(self, slug):
        "Returns blog equal to the given slug"
        sql = "SELECT * from blogs WHERE slug = (%s)"
        self.c.execute(sql, (slug, ))
        data = self.c.fetchone()
        # if fethchone fails, ie no slug exists in table, data == None
        if data is None:
            return None
        return Blog(data[0], data[1], data[2], data[3], data[4], data[5])
    
    def save(self, title, content, date):
        "Saves a newly created blog post"
        slug = slugify.slugify(title)
        excerpt = content[0:100] + "..."
        # test if slug doesnt already exist, then insert
        if self.get_slug(slug) is not None:
            return False
        sql = "INSERT INTO blogs (slug,title,content,excerpt,date) values (%s,%s,%s,%s,%s)"
        self.c.execute(sql, (slug, title, content, excerpt, date))
        self.conn.commit()
        return [True, slug]

    def get_images(self, slug):
        global client
        img_list = []
        poss_img = []

        all_objects = client.list_objects(Bucket='sam-app-bucket')
        for item in all_objects["Contents"]:
            poss_img.append(item["Key"])
        
        for f in poss_img:
            if slug.lower() in f:
                img_list.append(f)

        return img_list

    def delete(self, slug):
        "deletes a single blog post"
        global client
        sql = "DELETE from blogs WHERE slug = (%s)"
        # will come back and delete img here too.

        all_objects = client.list_objects(Bucket='sam-app-bucket')

        poss_img = []
        
        for item in all_objects["Contents"]:
            poss_img.append(item["Key"])
                
        for f in poss_img:
            if slug in f:
                client.delete_object(Bucket='sam-app-bucket', Key= f)

        self.c.execute(sql,(slug,))
        self.conn.commit()
    
    def view_table(self):
        "returns meta data about the table"
        sql = '''select column_name, data_type, character_maximum_length
                from INFORMATION_SCHEMA.COLUMNS where table_name = 'blogs';'''
        self.c.execute(sql)
        data = self.c.fetchall()

    def __del__(self):
        self.conn.close()

class Blog():
    "Err not sure on this class actually lol"
    def __init__(self, b_id, slug, title, content, excerpt, date):
        blogs = Blogs()
        self.id = b_id
        self.slug = slug
        self.title = title
        self.content = markdown.markdown(content)
        self.excerpt = markdown.markdown(excerpt)
        self.date = date
        self.imgs = blogs.get_images(slug)
        
@app.route("/")
def index():
    # will comeback and make this discoverable.
    blogs = Blogs()
    return render_template("index.html", data = blogs.get_all())

@app.route("/blog/<slug>")
def blog(slug):
    blogs = Blogs()
    blog = blogs.get_slug(slug)
    if blog is None: 
        return abort(404) 
    return render_template("hello.html", blog = blog)

@app.route("/api/all_blogs")
def api_all_blogs():
    blogs = Blogs()
    data = blogs.get_all()  
    return_arr = []

    for blog in data:
        temp = {}
        temp["title"] = blog.title
        temp["excerpt"] = blog.excerpt
        temp["slug"] = blog.slug
        temp["content"] = blog.content
        temp["date"] = blog.date
        temp["id"] = blog.id
        temp["img"] = blogs.get_images(blog.slug)

        return_arr.append(temp)
    
    return jsonify(result = True, data = return_arr)

@app.route("/api/single_blog", methods=['POST'])
def single_blog():
    form = request.form
    slug = form["slug"]
    blogs = Blogs()
    data = blogs.get_slug(slug)

    if data is not None:
        temp = {}
        temp["title"] = data.title
        temp["excerpt"] = data.excerpt
        temp["slug"] = data.slug
        temp["content"] = data.content
        temp["date"] = data.date
        temp["id"] = data.id
        temp["imgs"] = data.imgs

        return jsonify(result = True, data = temp)

    return jsonify(result = False)

@app.route("/api/create_post", methods=['POST'])
def api_create_post():
    blogs = Blogs()
    form = request.form
    title = form["title"]
    date = form["date"]
    content = form["content"]
    res = blogs.save(title, content, date)
    return jsonify(result = res[0], slug = res[1])

@app.route("/api/delete_post", methods=['POST'])
def api_delete_post():
    blogs = Blogs()
    form = request.form
    slug = form["slug"]
    blogs.delete(slug)
    return jsonify(result = True)

@app.route("/api/create_slug", methods=['POST'])
def api_create_slug():
    title = request.form["title"]
    slug = slugify.slugify(title)
    return jsonify(result = True, data = slug)

@app.route("/api/edit_post", methods=['POST'])
def api_edit_post():
    blogs = Blogs()
    form = request.form
    slug = form["slug"]
    title = form["title"]
    date = form["date"]
    content = form["content"]
    # res = blogs.save(title, content, date)
    return jsonify(result = True)

@app.route("/api/signin", methods=['POST'])
def api_signin():
    if str(request.form["password"]) == "sam":
        print("session now true")
        session["admin"] = True
        print(session.get("admin"))
        return jsonify(result = True)

    return jsonify(result = False)

@app.route("/api/signout")
def api_signout():
    session.clear()
    return jsonify(result = True)

@app.route("/api/current_user")
def api_current_user():
    print(session.get("admin"))
    return jsonify(result = session.get("admin"))

@app.route("/api/send_mail" , methods=['POST'])
def api_send_mail():
    form = request.form
    print(form)
    name = form["name"]
    email = form["email"]
    content = form["content"]

    with app.app_context():
        msg = Message('New Contact from samgriffen.com', sender=os.environ['GMAIL_PRIMARY_EMAIL'], recipients=[os.environ['GMAIL_PRIMARY_EMAIL']])
        msg.html = "<p><b>From:</b> " + name +"</p></br><p><b>Email:</b> " + email +"</p><p><b>Content:</b> " + content +"</p>"
        mail.send(msg)
        return jsonify(result = True)

@app.route("/api/upload_cover", methods=['GET','POST'])
def api_upload_cover():
    global client
    if request.method == 'POST':
        # check if the post request has the file part
        if 'file[]' not in request.files:
            return jsonify(result = False)
        files = dict(request.files)['file[]']
        print(files)
        # if user does not select file, browser also
        # submit a empty part without filename
        for f in files:
            print(f.filename)
            if f.filename == '':
                return jsonify(result = False)
            # custom blog file names
            filename = secure_filename(f.filename)
            print("BODY")
            print(f)
            client.put_object(Key='blog_imgs/' + filename, Body=f, Bucket="sam-app-bucket")
        return jsonify(result = True)
   
if __name__ == "__main__": #in prod dont actually run app.py, but in dev need this to run code below.
    app.run(debug=True) 