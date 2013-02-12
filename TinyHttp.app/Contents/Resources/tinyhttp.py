#!/usr/bin/env python

# vim:fdm=marker sw=4 ts=4 ft=python expandtab:

import socket,sys
import cgi, os
import BaseHTTPServer,CGIHTTPServer
import cgitb; cgitb.enable()
import urllib, posixpath
import select, copy

class TimeoutableHTTPServer(BaseHTTPServer.HTTPServer):
    timeout = 60.0
    """HTTPServer class with timeout."""

    def get_request(self):
        """Get the request and client address from the socket."""
        # 10 second timeout
        self.socket.settimeout(self.timeout)
        result = None
        while result is None:
            try:
                result = self.socket.accept()
            except socket.timeout:
                pass
        # Reset timeout on the new socket
        result[0].settimeout(None)
        return result

class PHPCGIHTTPRequestHandler(CGIHTTPServer.CGIHTTPRequestHandler):

    php_initialized = False
    php_bin = 'php-cgi'
    php_bin_fallback = 'php'

    indices = [
            'index.html',
            'index.xhtml',
            'index.cgi',
            'index.php',
            'index.pl',
            'index.py',
            'index.rb',
            ]
    aliases = [
            ('/', './'),
            ]
    actions = {
            'application/x-httpd-php': '',
            #'application/x-httpd-php': '/usr/bin/php',
            }

    CGIHTTPServer.CGIHTTPRequestHandler.extensions_map.update({
        '.php': 'application/x-httpd-php',
        })

    def init_bin(self):
        if not self.php_initialized:
            self.php_bin = self.which(self.php_bin)
            if not self.php_bin:
                self.php_bin = self.which(self.php_bin_fallback)

    def which(self, file):
        for path in os.environ["PATH"].split(":"):
            if os.path.exists(path + "/" + file):
                    return path + "/" + file
        return None

    def is_cgi(self):
        path = self.path
        i = path.rfind('?')
        if i >= 0:
            path, query = path[:i], path[i:]
        else:
            query = ''
        root, ext = os.path.splitext(path)
        if ext == ".pl" or ext == ".cgi":
            self.cgi_info = CGIHTTPServer._url_collapse_path_split(self.path)
            return True
        if ext == ".php":
            self.cgi_info = CGIHTTPServer._url_collapse_path_split(self.path)
            return True
        if ext == ".py":
            self.cgi_info = CGIHTTPServer._url_collapse_path_split(self.path)
            return True
        if ext == ".rb":
            self.cgi_info = CGIHTTPServer._url_collapse_path_split(self.path)
            return True
        return False

    def do_HEAD(self):
        self.redirect_path()
        CGIHTTPServer.CGIHTTPRequestHandler.do_HEAD(self)

    def do_GET(self):
        self.redirect_path()
        if self.is_cgi():
            self.run_cgi()
        else:
            # super(ExCGIHTTPRequestHandler, self).do_GET()
            CGIHTTPServer.CGIHTTPRequestHandler.do_GET(self)

    def do_POST(self):
        self.redirect_path()
        if self.is_cgi():
            self.run_cgi()
        else:
            self.send_error(501, "Can only POST to CGI scripts")

    def run_cgi(self):
        # root, ext = os.path.splitext(self.path)
        # path = self.translate_path(self.path)
        # orig_mod = os.stat(path).st_mode & 0777
        # if ext == ".php":
        #     os.chmod(self.path, 0755)
        # super(ExCGIHTTPRequestHandler, self).run_cgi()
        CGIHTTPServer.CGIHTTPRequestHandler.run_cgi(self)
        # if ext == ".php":
        #     os.chmod(path, orig_mod)


    def run_cgi(self):
        """Execute a CGI script."""
        path = self.path
        dir, rest = self.cgi_info

        i = path.find('/', len(dir) + 1)
        while i >= 0:
            nextdir = path[:i]
            nextrest = path[i+1:]

            scriptdir = self.translate_path(nextdir)
            if os.path.isdir(scriptdir):
                dir, rest = nextdir, nextrest
                i = path.find('/', len(dir) + 1)
            else:
                break

        # find an explicit query string, if present.
        i = rest.rfind('?')
        if i >= 0:
            rest, query = rest[:i], rest[i+1:]
        else:
            query = ''

        # dissect the part after the directory name into a script name &
        # a possible additional path, to be stored in PATH_INFO.
        i = rest.find('/')
        if i >= 0:
            script, rest = rest[:i], rest[i:]
        else:
            script, rest = rest, ''

        scriptname = dir + '/' + script
        scriptfile = self.translate_path(scriptname)
        if not os.path.exists(scriptfile):
            self.send_error(404, "No such CGI script (%r)" % scriptname)
            return
        if not os.path.isfile(scriptfile):
            self.send_error(403, "CGI script is not a plain file (%r)" %
                            scriptname)
            return
        ispy = self.is_python(scriptname)
        isphp = self.is_php(scriptname)
        if not (ispy or isphp):
            if not (self.have_fork or self.have_popen2 or self.have_popen3):
                self.send_error(403, "CGI script is not a Python script (%r)" %
                                scriptname)
                return
            if not self.is_executable(scriptfile):
                self.send_error(403, "CGI script is not executable (%r)" %
                                scriptname)
                return

        # Reference: http://hoohoo.ncsa.uiuc.edu/cgi/env.html
        # XXX Much of the following could be prepared ahead of time!
        env = copy.deepcopy(os.environ)
        env['SERVER_SOFTWARE'] = self.version_string()
        env['SERVER_NAME'] = self.server.server_name
        env['GATEWAY_INTERFACE'] = 'CGI/1.1'
        env['SERVER_PROTOCOL'] = self.protocol_version
        env['SERVER_PORT'] = str(self.server.server_port)
        env['REQUEST_METHOD'] = self.command
        uqrest = urllib.unquote(rest)
        env['PATH_INFO'] = uqrest
        env['PATH_TRANSLATED'] = self.translate_path(uqrest)
        env['SCRIPT_NAME'] = scriptname
        if query:
            env['QUERY_STRING'] = query
        host = self.address_string()
        if host != self.client_address[0]:
            env['REMOTE_HOST'] = host
        env['REMOTE_ADDR'] = self.client_address[0]
        authorization = self.headers.getheader("authorization")
        if authorization:
            authorization = authorization.split()
            if len(authorization) == 2:
                import base64, binascii
                env['AUTH_TYPE'] = authorization[0]
                if authorization[0].lower() == "basic":
                    try:
                        authorization = base64.decodestring(authorization[1])
                    except binascii.Error:
                        pass
                    else:
                        authorization = authorization.split(':')
                        if len(authorization) == 2:
                            env['REMOTE_USER'] = authorization[0]
        # XXX REMOTE_IDENT
        if self.headers.typeheader is None:
            env['CONTENT_TYPE'] = self.headers.type
        else:
            env['CONTENT_TYPE'] = self.headers.typeheader
        length = self.headers.getheader('content-length')
        if length:
            env['CONTENT_LENGTH'] = length
        referer = self.headers.getheader('referer')
        if referer:
            env['HTTP_REFERER'] = referer
        accept = []
        for line in self.headers.getallmatchingheaders('accept'):
            if line[:1] in "\t\n\r ":
                accept.append(line.strip())
            else:
                accept = accept + line[7:].split(',')
        env['HTTP_ACCEPT'] = ','.join(accept)
        ua = self.headers.getheader('user-agent')
        if ua:
            env['HTTP_USER_AGENT'] = ua
        co = filter(None, self.headers.getheaders('cookie'))
        if co:
            env['HTTP_COOKIE'] = ', '.join(co)
        # XXX Other HTTP_* headers
        # Since we're setting the env in the parent, provide empty
        # values to override previously set values
        for k in ('QUERY_STRING', 'REMOTE_HOST', 'CONTENT_LENGTH',
                  'HTTP_USER_AGENT', 'HTTP_COOKIE', 'HTTP_REFERER'):
            env.setdefault(k, "")

        self.send_response(200, "Script output follows")

        decoded_query = query.replace('+', ' ')

        if self.is_php(scriptfile):
            env['SCRIPT_FILENAME'] = os.path.abspath(scriptfile)
            self.init_bin()

        # if self.have_fork and not self.is_php(scriptfile):
        if self.have_fork:
            # Unix -- fork as we should
            args = [script]
            if self.is_php(scriptfile):
                args = [scriptfile]
                scriptfile = self.php_bin
            #     args = [scriptfile]
            #     scriptfile = '/usr/bin/php'
            if '=' not in decoded_query:
                args.append(decoded_query)
            nobody = CGIHTTPServer.nobody_uid()
            self.wfile.flush() # Always flush before forking
            pid = os.fork()
            if pid != 0:
                # Parent
                pid, sts = os.waitpid(pid, 0)
                # throw away additional data [see bug #427345]
                while select.select([self.rfile], [], [], 0)[0]:
                    if not self.rfile.read(1):
                        break
                if sts:
                    self.log_error("CGI script exit status %#x", sts)
                return
            # Child
            try:
                # try:
                #     os.setuid(nobody)
                # except os.error:
                #     pass
                os.dup2(self.rfile.fileno(), 0)
                os.dup2(self.wfile.fileno(), 1)
                os.execve(scriptfile, args, env)
            except:
                self.server.handle_error(self.request, self.client_address)
                os._exit(127)

        else:
            # Non Unix - use subprocess
            import subprocess
            cmdline = [scriptfile]
            if self.is_python(scriptfile):
                interp = sys.executable
                if interp.lower().endswith("w.exe"):
                    # On Windows, use python.exe, not pythonw.exe
                    interp = interp[:-5] + interp[-4:]
                cmdline = [interp, '-u'] + cmdline
            if self.is_php(scriptfile):
                cmdline = [self.php_bin] + cmdline

            if '=' not in query:
                cmdline.append(query)

            self.log_message("command: %s", subprocess.list2cmdline(cmdline))
            try:
                nbytes = int(length)
            except (TypeError, ValueError):
                nbytes = 0
            p = subprocess.Popen(cmdline,
                                 stdin = subprocess.PIPE,
                                 stdout = subprocess.PIPE,
                                 stderr = subprocess.PIPE,
                                 env = env
                                )
            if self.command.lower() == "post" and nbytes > 0:
                data = self.rfile.read(nbytes)
            else:
                data = None
            # throw away additional data [see bug #427345]
            while select.select([self.rfile._sock], [], [], 0)[0]:
                if not self.rfile._sock.recv(1):
                    break
            stdout, stderr = p.communicate(data)
            self.wfile.write(stdout)
            if stderr:
                self.log_error('%s', stderr)
            p.stderr.close()
            p.stdout.close()
            status = p.returncode
            if status:
                self.log_error("CGI script exit status %#x", status)
            else:
                self.log_message("CGI script exited OK")

    def redirect_path(self):
        path = self.path
        i = path.rfind('?')
        if i >= 0:
            path, query = path[:i], path[i:]
        else:
            query = ''

        head, tail = path, ''
        temp = self.translate_path(head)
        while not os.path.exists(temp):
            i = head.rfind('/')
            if i < 0:
                break
            head, tail = head[:i], head[i:] + tail
            temp = self.translate_path(head)

        if os.path.isdir(temp):
            for index in self.indices:
                if os.path.exists(os.path.join(temp, index)):
                    head = posixpath.join(head, index)
                    break

        ctype = self.guess_type(head)
        if ctype in self.actions:
            os.environ['REDIRECT_STATUS'] = '200'
            head = self.actions[ctype] + head

        self.path = head + tail + query

    def translate_path(self, path):
        path = posixpath.normpath(urllib.unquote(path))
        n = len(self.aliases)
        for i in range(n):
            url, dir = self.aliases[n-i-1]
            length = len(url)
            if path[:length] == url:
                return dir + path[length:]
        return ''

    def is_php(self, path):
        root, ext = os.path.splitext(path)
        return ext == ".php"


server = TimeoutableHTTPServer
handler = PHPCGIHTTPRequestHandler

# server = BaseHTTPServer.HTTPServer
# handler = CGIHTTPServer.CGIHTTPRequestHandler

for port in range(50080, 65535):
    try:
        httpd = server(( '0.0.0.0', port ), handler )
        sa = httpd.socket.getsockname()
        print("starting sever - http://%s:%d" % (sa[0], sa[1]))
        # CGIHTTPServer.test(handler, server)
        httpd.serve_forever()
        break
    except KeyboardInterrupt:
        print "error:", sys.exc_info()[0]
        break
    except socket.error:
        print "Unexpected error:", sys.exc_info()[0]

# import socket,sys
# import cgi
# import BaseHTTPServer,CGIHTTPServer
#
# # CGIHTTPServer.CGIHTTPRequestHandler.cgi_directories = ['/']
# for port in range(50080, 65535):
#     try:
#         print("starting sever - http://localhost:%d" % port)
#         BaseHTTPServer.HTTPServer(( '0.0.0.0', port ), CGIHTTPServer.CGIHTTPRequestHandler ).serve_forever()
#         break
#     except socket.error:
#         print "Unexpected error:", sys.exc_info()[0]

