import java.util.Scanner;

public class DecimalToBinary {
    public static void toBinary(int x, char[] out, int width) {
        for (int i = width - 1; i >= 0; --i) {
            out[i] = (x & 1) == 1 ? '1' : '0';
            x >>= 1;
        }
        out[width] = '\0';
    }

    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int n = scanner.nextInt();
        for (int i = 0; i < n; ++i) {
            int v = scanner.nextInt();
            char[] buf = new char[16];
            toBinary(v, buf, 8);
            System.out.print(v + " -> ");
            for (int j = 0; buf[j] != '\0'; j++) System.out.print(buf[j]);
            System.out.println();
        }
        scanner.close();
    }
}