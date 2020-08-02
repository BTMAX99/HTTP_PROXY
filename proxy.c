#include <stdio.h>
#include "proxy_parse.h"
#include <stdlib.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <netinet/in.h>
#include <netdb.h>
#include <string.h>

int child_no=0;

int Create_server_socket(char *port_no)
{
	int server_fd;
	struct addrinfo hints,*serv_addr;
	memset(&hints, 0, sizeof(hints));
	hints.ai_family = AF_INET;
	hints.ai_socktype = SOCK_STREAM;
	int av = getaddrinfo(NULL, port_no, &hints, &serv_addr);
	if(av<0) //if address is invalid
	{
		printf("invalid address");
		exit(0);
	}
	server_fd = socket(serv_addr->ai_family,serv_addr->ai_socktype,serv_addr->ai_protocol);
	
	if(server_fd < 0)//if socket is not properly created
	{
		printf("socket creation failed");
		exit(0);
	}
	  
    int bv = bind(server_fd,serv_addr->ai_addr,serv_addr->ai_addrlen);
    if(bv < 0)//when bind fails
    {
    	printf("Bind failed");
    	exit(0);
    }
    int lv = listen(server_fd,3);
	if(lv < 0)//when listen fails
	{
	    printf("Listen failed");
	    exit(0);
	}
	freeaddrinfo(serv_addr);
	return server_fd;
}
int Create_client_socket(char* serv_address , char* port_no)
{
	int client_fd;
	struct addrinfo hints,*address;
	memset(&hints, 0, sizeof(hints));
	hints.ai_family = AF_UNSPEC;
	hints.ai_socktype = SOCK_STREAM;
	int av = getaddrinfo(serv_address,port_no,&hints,&address);
	if(av < 0)//error in getting address information
	{
		printf("Invalid address");
		exit(0);
	}
	//create socket
	client_fd = socket(address->ai_family,address->ai_socktype,address->ai_protocol);
	if(client_fd < 0)//error in creating socket
	{
		printf("Create error");
		exit(0);
	}
	//connect
	int cv = connect(client_fd,address->ai_addr,address->ai_addrlen);
	if(cv < 0)//error in connecting
	{
		printf("Connect error");
		exit(0);
	}
	freeaddrinfo(address);
	return client_fd;
}
char *get_server_request(struct ParsedRequest *parsedrequest,int cf,int *len)
{
	char* s_req;
	char* buffer;
	int h_len;
	ParsedHeader_set(parsedrequest, "Host", parsedrequest->host);
	ParsedHeader_set(parsedrequest, "Connection", "close");

	h_len = ParsedHeader_headersLen(parsedrequest);
	buffer = (char *)malloc(h_len+1);



	ParsedRequest_unparse_headers(parsedrequest,buffer,h_len);
	buffer[h_len] = '\0';
	*len = strlen(parsedrequest->method)+strlen(parsedrequest->path)+strlen(parsedrequest->version)+h_len+4; //4 because of 2 spaces and \r\n
	s_req = (char *)malloc(*len+1);
	s_req[0] = '\0';
	char* sm = parsedrequest->method;
	char* sp = parsedrequest->path;
	char* sv = parsedrequest->version;
	strcpy(s_req, sm);
	strcat(s_req, " ");
	strcat(s_req, sp);
	strcat(s_req, " ");
	strcat(s_req, sv);
	strcat(s_req, "\r\n");
	strcat(s_req, buffer);
	free(buffer);//freeing buffer
	return s_req;
}
void WriteToSocket(char* buff,int *len,int sockfd ,int othersockfd)//writing buffer to socket
{
	int temp=0;
	while(temp < *len)
	{
		int temp1=0;
		temp1 = send(sockfd,(void *) (buff+temp),*len-temp,0);
		if(temp1<0)//error in send
		{
			printf("Send error");
			shutdown(sockfd,SHUT_RDWR);
			close(sockfd);
			if(othersockfd != 0)
			{
				shutdown(othersockfd,SHUT_RDWR);
				close(othersockfd);
			}
			exit(EXIT_FAILURE);
		}
		temp += temp1;
	}
}


char *get_client_request(int sf)
{
	int bsize = 5000;//buffer size
	char *req;
	req = (char *)malloc(bsize+1);
	char buffer[bsize+1];
	int rv;
	int temp1,temp2;
	temp1 = 0;
	temp2 = bsize;
	while(strstr(req, "\r\n\r\n") == NULL)//while loop continues until it finds \r\n\r\n in req
	{
		rv = recv(sf,buffer,bsize,0); //receiving from client
		if(rv==0){break;}
		if(rv<0) //if receiving is failed
		{
			int e_len = 20;
			char err[16]="Receiving error";
			WriteToSocket(err,&e_len, sf, -1);
			shutdown(sf, SHUT_RDWR);
			close(sf);
			exit(0);
		}
		buffer[rv]='\0';
		temp1=temp1+rv;
		if(temp1>temp2) //if req size is insufficient reallocate 
		{
			temp2 = temp2*2;
			req = (char *)realloc(req,temp2+1);
		}
		strcat(req,buffer); //concatinating
	}
	return req;
}
void opfunction(int cf,int sf)
{
	fflush(NULL); //The system flushes all open streams. 
	int pid=fork();
	if(pid == -1)
	{
		shutdown(cf, SHUT_RDWR);
		close(cf);
		printf("Error in fork\n");
		return;
	}
	if(pid == 0)//child process
	{
		close(sf);
		int ser_fd;
		char *c_req;//client request
		char *s_req;//server request
		struct  ParsedRequest *parsedrequest; //ParsedRequest structure for storing parsed values from client request
		int temp = 0;
		int *parsedrequest_len = &temp;
		c_req = get_client_request(cf);//ge request from client socket
		parsedrequest = ParsedRequest_create();
		int pv;
		pv = ParsedRequest_parse(parsedrequest,c_req,strlen(c_req)); //parsing c_req
		if(parsedrequest->port==NULL)//setting default port
		{
			char def_port[3] = "80";
			parsedrequest->port = def_port;
		}
		if(pv<-1)//c_req not implemented
		{
			int e_len = 20;
			char err[16]="Not Implemented";
			WriteToSocket(err,&e_len,cf,0);
			shutdown(cf,SHUT_RDWR);
			close(cf);
			exit(0);
		}
		else if(pv < 0)//c_req is a bad request
		{
			int e_len = 15;
			char err[12]="Bad request";
			WriteToSocket(err,&e_len,cf,0);
			shutdown(cf,SHUT_RDWR);
			close(cf);
			exit(0);
		}
		s_req  = get_server_request(parsedrequest,cf,parsedrequest_len);//converting parsed request to server expected request form
		ser_fd = Create_client_socket(parsedrequest->host,parsedrequest->port);//creating client socket with port number and address that came from parsing
		WriteToSocket(s_req,parsedrequest_len,ser_fd,cf);//writing s_req to server socket

		int bsize = 5000;
		char buffer[bsize];
		int rv;
		while ((rv = recv(ser_fd,buffer,bsize, 0)) > 0)//receiving reply from server socket
		{
	     	WriteToSocket(buffer,&rv,cf,ser_fd);//writing received reply to client socket
 		} 
		if(rv < 0)//error in receiving
		{
			int e_len = 20;
			char err[16] = "Receiving error";
			WriteToSocket(err,&e_len,cf,ser_fd);
		  shutdown(cf, SHUT_RDWR);
		  shutdown(ser_fd, SHUT_RDWR);
		  close(cf);
		  close(ser_fd);
		  exit(0);
		}
		ParsedRequest_destroy(parsedrequest);

		shutdown(cf, SHUT_RDWR);
		shutdown(ser_fd, SHUT_RDWR);
		free(c_req);
		free(s_req);
		close(ser_fd);
		close(cf);
		exit(0);
	}
	child_no++;
	if(child_no>=3)//When more than 3 clients are accessing
	{
		printf("More than 3 clients can't access\n");
		exit(0);
	}
	
}
int main(int argc,char* argv[])
{
	//argv[1] is  port number specified
	char *port_no = argv[1];
	struct sockaddr client_addr;//for client address
	socklen_t len = sizeof(struct sockaddr);
	if(argc!=2)//if arguments are not given correctly
	{
		printf("PLEASE SPECIFY PORT NUMBER\n" );
		exit(0);
	}
	int sock_fd, client_fd;//sokets
	sock_fd = Create_server_socket(port_no);//creating a new socket using given port number
	while(true)
	{
		client_fd = accept(sock_fd,&client_addr,&len);//client_fd is a new socket connected to sock_fd 
		if(client_fd < 0)
		{
			shutdown(client_fd,SHUT_RDWR);
			close(client_fd);
			continue;
		} 
		opfunction(client_fd,sock_fd);//for processing the requests from client  
	}

	return 0;
}
