include ../../Rules.mak
CC=$(CROSS)gcc

CFLAGS  = -Os -s -Wall
CFLAGS += -Werror
CFLAGS += -DTEST

ifeq ($(BOOT_NAND_FLASH),1)
CFLAGS += -DBOOT_NAND_FLASH
endif

DESTLIB = ../../target/lib
DESTBIN = ../../target/usr/sbin

BIN=njmserver

all: $(BIN)

njmserver.o : njmserver.c
	$(CC) $(CFLAGS) -fPIC -g -c $^ -o $@

clean:
	rm -rf *~ *.o *.so njmserver
