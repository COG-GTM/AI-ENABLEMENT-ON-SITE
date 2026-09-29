/* Linker script for the target part: flash at 0x08000000, RAM at 0x20000000. */
MEMORY
{
  FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 512K
  RAM  (rwx) : ORIGIN = 0x20000000, LENGTH = 128K
}
