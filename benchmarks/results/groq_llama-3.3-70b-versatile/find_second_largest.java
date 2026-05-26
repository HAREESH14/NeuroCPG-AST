import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int n = scanner.nextInt();
        if (n > 100) n = 100;
        int[] a = new int[n];
        for (int i = 0; i < n; ++i) {
            a[i] = scanner.nextInt();
        }
        int max = a[0], second = a[0];
        for (int i = 1; i < n; ++i) {
            if (a[i] > max) { 
                second = max; 
                max = a[i]; 
            }
            else if (a[i] > second && a[i] < max) second = a[i];
        }
        System.out.println("Max: " + max + ", Second max: " + second);
    }
}