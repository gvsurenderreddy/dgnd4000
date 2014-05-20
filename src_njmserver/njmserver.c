#include <stdbool.h>
#include <stdlib.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>
#include <sys/wait.h>
#include <signal.h>
#include <time.h>
#include <sys/time.h>
#include <ctype.h>

int DEBUG = false;

void logmsg(const char *format, ...)
{
	va_list arguments;
	va_start (arguments, format);

	struct timeval now;
	if (gettimeofday(&now, NULL) == 0)
	{
	    char buff[100];
	    strftime (buff, 100, "%Y-%m-%d %H:%M:%S", localtime(&now.tv_sec));
	    printf ("%s.%06u: ", buff, (uint)now.tv_usec);
	}
    vprintf(format, arguments);

	va_end (arguments);
}

bool doprocessing (int sock)
{
    int n;
	char output[1024];
	char *s;
	FILE *fpo;
    char cmd[256];

    bzero(cmd, 256);
    n = read(sock, cmd, 255);
    if (n < 0)
    {
        perror("ERROR reading from socket");
        exit(1);
    }

	s = strchr(cmd, '\n');
	if (s != NULL) *s = '\0';
	s = strchr(cmd, '\r');
	if (s != NULL) *s = '\0';

	if (DEBUG) logmsg("Received command: %s\n", cmd);
	if (strcmp("quit", cmd) == 0) return false;

	if (strchr(cmd, '|') == NULL && (strstr(cmd, "cat ") - cmd) == 0)
	{
		char *filename = cmd;
		while (!isspace(*(++filename)));
		while (isspace(*(++filename)));
		if (DEBUG) logmsg("Reading file: %s\n", filename);

 		if ((fpo = fopen(filename,"r")) == NULL)
 		{
			strcpy(output, "Error!");
			n = write(sock,output,strlen(output));
			if (n < 0)
			{
				perror("ERROR writing to socket");
			}
		}
		else
		{
			while((s = fgets(output, 1024, fpo)) != NULL)
			{
				n = write(sock,output,strlen(output));
				if (n < 0)
				{
					perror("ERROR writing to socket");
					break;
				}
			}
		}
		fclose(fpo);
	}
	else
	{
		if (DEBUG) logmsg("Executing command: %s\n", cmd);

		if ((fpo = popen((const char*)&cmd, "r")) == NULL)
		{
			strcpy(output, "Error!");
			n = write(sock,output,strlen(output));
			if (n < 0)
			{
				perror("ERROR writing to socket");
			}
		}
		else
		{
			while((s = fgets(output, 1024, fpo)) != NULL)
			{
				n = write(sock,output,strlen(output));
				if (n < 0)
				{
					perror("ERROR writing to socket");
					break;
				}
			}
		}
		pclose(fpo);
	}

	return true;
}

void catch(int snum)
{
	pid_t pid;
	int status;
	int exitcode, exitcode_tmp;

	pid = wait(&status);
	exitcode = WEXITSTATUS(status);

	if (DEBUG) logmsg("parent: child process exited with value %d\n", WEXITSTATUS(status));

	// Reap all pending child processes (ie. mop up any zombies)
    do {
        pid = waitpid((pid_t)-1, &status, WNOHANG);
        if (pid != (pid_t)0 && pid != (pid_t)-1)
        {
			exitcode_tmp = WEXITSTATUS(status);
			if (exitcode_tmp > exitcode) exitcode = exitcode_tmp;
		}
		else
			break;
    } while (1);

	if (exitcode == 1)
	{
		if (DEBUG) logmsg("parent: quitting\n");
		exit(1);
	}
}

int doserver( int lport)
{
	int sockfd, newsockfd, portno;
	socklen_t clilen;
	struct sockaddr_in serv_addr, cli_addr;

	// First call to socket() function
	sockfd = socket(AF_INET, SOCK_STREAM, 0);
	if (sockfd < 0)
	{
		perror("ERROR opening socket");
		exit(1);
	}

	// set SO_REUSEADDR on a socket to true (1):
	int optval = 1;
	setsockopt(sockfd, SOL_SOCKET, SO_REUSEADDR, &optval, sizeof optval);

	// Initialize socket structure
	bzero((char *) &serv_addr, sizeof(serv_addr));
	portno = lport;
	serv_addr.sin_family = AF_INET;
	serv_addr.sin_addr.s_addr = INADDR_ANY;
	serv_addr.sin_port = htons(portno);

	// Now bind the host address using bind() call
	if (bind(sockfd, (struct sockaddr *) &serv_addr,
						  sizeof(serv_addr)) < 0)
	{
		 perror("ERROR on binding");
		 exit(1);
	}

	if (DEBUG) logmsg("Listening on port %d\n", lport);

	/* Now start listening for the clients, here
	 * process will go in sleep mode and will wait
	 * for the incoming connection
	 */
	listen(sockfd,5);
	clilen = sizeof(cli_addr);

	struct sigaction act;
	memset (&act, 0, sizeof(act));
	act.sa_handler = catch;
	act.sa_flags = SA_RESTART;
	if (sigaction(SIGCHLD, &act, NULL)) // detect child termination
	{
		perror ("sigaction (parent)");
		exit(1);
	}

	while (1)
	{
		newsockfd = accept(sockfd,
				(struct sockaddr *) &cli_addr, &clilen);
		if (newsockfd < 0)
		{
			perror("ERROR on accept");
			exit(1);
		}
		// Create child process
		pid_t pid = fork();
		if (pid < 0)
		{
			perror("ERROR on fork");
			exit(1);
		}
		else if (pid == 0)
		{
			// This is the child process
			act.sa_handler = SIG_IGN;
			if (sigaction(SIGCHLD, &act, NULL))  // don't detect further child terminations
			{
				perror ("sigaction (child)");
				exit(1);
			}
			close(sockfd);
			if (doprocessing(newsockfd))
				exit(0);
			else
				exit(1);
		}
		close(newsockfd);
	} // end of while
}

int main( int argc, char *argv[] )
{
    if ( argc < 2 ) // argc should be 2 for correct execution
	{
 		printf( "Usage: %s port [debug]\n", argv[0] );
	}
	else
	{
		DEBUG = (argc==3 && strcmp("debug", argv[2])==0);
		doserver(atoi(argv[1]));
	}
	return 1;
}
